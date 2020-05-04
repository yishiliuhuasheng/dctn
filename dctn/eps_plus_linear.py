from functools import reduce
import operator
from typing import Tuple, Dict, Union

from more_itertools import intersperse
from attr import attrs, attrib

import torch
from torch import Tensor
import torch.nn as nn

from einops.layers.torch import Rearrange
from einops import rearrange

from . import eps
from .eps import EPS
from . import epses_composition
from .utils import (
    ZeroCenteredNormalInitialization,
    ZeroCenteredUniformInitialization,
    OneTensorInitialization,
)


@attrs(auto_attribs=True, frozen=True)
class UnitEmpiricalOutputStd:
    input: Tensor
    batch_size: int = attrib(default=128)


class UnitTheoreticalOutputStd:
    pass


@attrs(auto_attribs=True, frozen=True)
class ManuallyChosenInitialization:
    epses: Tuple[OneTensorInitialization]
    linear_weight: OneTensorInitialization
    linear_bias: OneTensorInitialization


Initialization = Union[
    UnitEmpiricalOutputStd, UnitTheoreticalOutputStd, ManuallyChosenInitialization
]


class EPSesPlusLinear(nn.Module):
    def __init__(
        self,
        epses_specs: Tuple[Tuple[int, int]],
        initialization: Initialization,
        p: float,
        device: torch.device,
        dtype: torch.dtype,
    ):
        """`p` is the probability of not dropping a tensor's component."""
        assert 0.0 < p <= 1
        super().__init__()
        if isinstance(initialization, UnitEmpiricalOutputStd):
            epses = epses_composition.make_epses_composition_unit_empirical_output_std(
                epses_specs, initialization.input, device, dtype, initialization.batch_size
            )

        elif isinstance(initialization, UnitTheoreticalOutputStd):
            epses = epses_composition.make_epses_composition_unit_theoretical_output_std(
                epses_specs, 2, device, dtype
            )
        elif isinstance(initialization, ManuallyChosenInitialization):
            # TODO change this
            epses = tuple(
                epses_composition.make_epses_composition_manually_chosen_inializations(
                    epses_specs, initialization.epses, 2, device, dtype
                )
            )
        else:
            raise ValueError(f"{initialization=} is not {Initialization}")
        self.epses = nn.ParameterList(nn.Parameter(eps_core) for eps_core in epses)

        # initialize the linear layer
        pre_linear_image_height = (
            28 - sum(kernel_sizes := tuple(ks for ks, _ in epses_specs)) + len(kernel_sizes)
        )
        pre_linear_image_width = pre_linear_image_height
        self.linear = nn.Linear(
            pre_linear_image_height
            * pre_linear_image_width
            * eps.matrix_shape(self.epses[-1])[0],
            10,
            bias=True,
        ).to(dtype)
        if isinstance(initialization, ManuallyChosenInitialization):
            for param, param_initialization in zip(
                (self.linear.weight, self.linear.bias),
                (initialization.linear_weight, initialization.linear_bias),
            ):
                if isinstance(param_initialization, ZeroCenteredNormalInitialization):
                    new_data = torch.randn_like(param) * param_initialization.std
                elif isinstance(param_initialization, ZeroCenteredUniformInitialization):
                    new_data = (
                        torch.rand_like(param) * (2 * param_initialization.maximum)
                        - param_initialization.maximum
                    )
                else:
                    raise ValueError(
                        f"{initialization=} must be {ManuallyChosenInitialization}"
                    )
                param.data.copy_(new_data)

        else:
            self.linear.weight.data.copy_(
                torch.randn_like(self.linear.weight) * self.linear.in_features ** -0.5 / 4.0
            )
        self.linear.to(device)

        self.register_buffer("p", torch.tensor(p, device=device, dtype=dtype))

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        if self.p < 1.0 and self.training:
            epses = tuple(
                self.p.expand_as(eps_core).bernoulli() * eps_core / self.p
                for eps_core in self.epses
            )
        else:
            epses = self.epses
        intermediate = epses_composition.contract_with_input(epses, input)
        return self.linear(rearrange(intermediate, "b h w q -> b (h w q)"))

    def epswise_l2_regularizer(self) -> torch.Tensor:
        """Returns sum of squared frobenius norms of epses' cores and the weight of the last (linear) layer.
        Note: doesn't do anything with the bias of the last (linear) layer."""
        return self.linear.weight.norm(
            p="fro"
        ) ** 2 + epses_composition.epswise_squared_fro_norm(self.epses)

    def epses_composition_l2_regularizer(self) -> torch.Tensor:
        return self.linear.weight.norm(p="fro") ** 2 + epses_composition.inner_product(
            self.epses, self.epses
        )
