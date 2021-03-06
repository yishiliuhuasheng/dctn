import os.path
from typing import Tuple, Optional, Dict, Any, List

from bokeh.models import ColumnDataSource, Range1d, Slider, RangeSlider, Div
from bokeh.layouts import gridplot
from bokeh.plotting import save, output_file, figure, Figure

import click

from libcrap import load_json
from libcrap.visualization import get_distinguishable_colors

from dctn.visualization.log_parsing import Record, load_records


@click.command()
@click.argument("config-path", type=click.Path(exists=True, dir_okay=False, writable=False))
@click.argument("output-path", type=click.Path(exists=False, dir_okay=False, writable=True))
@click.option(
    "--experiments-base-dir",
    type=click.Path(exists=True, dir_okay=True, file_okay=False, writable=False),
    default="/mnt/important/experiments",
)
@click.option("--big-plots/--no-big-plots", default=False)
def main(config_path: str, output_path: str, experiments_base_dir, big_plots: bool):
    log_rel_fname = "log.log"
    run_info_rel_fname = "run_info.txt"
    run_info_useless_keys = frozenset(
        {
            "breakpoint_on_nan_loss",
            "commit",
            "device",
            "ds_path",
            "es_train_acc",
            "es_train_mean_ce",
            "es_val_acc",
            "es_val_mean_ce",
            "experiments_dir",
            "keep_last_models",
            "max_num_iters",
            "patience",
            "tb_batches",
            "verbosity",
        }
    )
    config: List[Dict[str, str]] = load_json(config_path)
    experiments_rel_dirs: Tuple[str, ...] = tuple(d["rel_dir"] for d in config["experiments"])
    experiments_names: Tuple[str, ...] = tuple(d["name"] for d in config["experiments"])
    experiments_descriptions: Tuple[str, ...] = tuple(
        d["description"] for d in config["experiments"]
    )

    runs_infos: Dict[str, Any] = tuple(
        {
            k: v
            for k, v in load_json(
                os.path.join(experiments_base_dir, experiment_rel_dir, run_info_rel_fname)
            ).items()
            if k not in run_info_useless_keys
        }
        for experiment_rel_dir in experiments_rel_dirs
    )

    assert len(experiments_names) == len(experiments_rel_dirs)
    colors = get_distinguishable_colors(len(experiments_names))

    all_increasing_tracc_records: Tuple[Tuple[Record, ...], ...] = tuple(
        load_records(
            os.path.join(experiments_base_dir, experiment_dir, log_rel_fname),
            increasing_tracc=True,
        )
        for experiment_dir in experiments_rel_dirs
    )

    all_records: Tuple[Tuple[Record, ...], ...] = tuple(
        load_records(
            os.path.join(experiments_base_dir, experiment_dir, log_rel_fname),
            increasing_tracc=False,
        )
        for experiment_dir in experiments_rel_dirs
    )

    # output_file("one_eps_vacc_by_tracc.html")
    output_file(output_path, mode="inline")

    tools = "pan,wheel_zoom,box_zoom,reset,crosshair,hover,undo,redo,save"

    tracc_range = Range1d(bounds=(0.0, 1.0))
    vacc_range = Range1d(bounds=(0.0, 1.0))
    nitd_range = Range1d(
        0,
        (maximum_nitd := max(records[-1].nitd for records in all_records)),
        bounds=(0, maximum_nitd),
    )
    min_mce = min(
        min(min(record.trmce for record in records) for records in all_records),
        min(min(record.vmce for record in records) for records in all_records),
    )
    max_mce = max(
        max(max(record.trmce for record in records) for records in all_records),
        max(max(record.vmce for record in records) for records in all_records),
    )
    trmce_range = Range1d(0.0, max_mce, bounds=(min_mce, max_mce))
    vmce_range = Range1d(0.0, max_mce, bounds=(min_mce, max_mce))

    # plot vacc by tracc
    vacc_by_tracc_plot = figure(
        x_axis_label="train acc",
        y_axis_label="val acc",
        tools=tools,
        x_range=tracc_range,
        y_range=vacc_range,
        **({"plot_height": 850, "plot_width": 1400} if big_plots else {}),
    )
    vacc_by_tracc_plot.line(
        (0.0, 1.0), (0.0, 1.0), line_color="black", alpha=0.3, line_dash="dashed"
    )
    for experiment_name, records, color in zip(
        experiments_names, all_increasing_tracc_records, colors
    ):
        vacc_by_tracc_plot.line(
            tuple(record.tracc for record in records),
            tuple(record.vacc for record in records),
            legend_label=experiment_name,
            line_color=color,
        )
    vacc_by_tracc_plot.legend.location = "top_left"
    vacc_by_tracc_plot.legend.click_policy = "hide"

    def plot_something_by_nitd(
        y_axis_label: str,
        y_range: Range1d,
        record_attr: str,
        legend_location: str,
        plot_height: Optional[int] = None,
    ) -> Figure:
        plot = figure(
            x_axis_label="number of iterations done",
            y_axis_label=y_axis_label,
            tools=tools,
            x_range=nitd_range,
            y_range=y_range,
            **(
                {"plot_height": 850, "plot_width": 1400}
                if big_plots
                else {"plot_height": plot_height}
            ),
        )
        for experiment_name, records, color in zip(experiments_names, all_records, colors):
            plot.line(
                tuple(record.nitd for record in records),
                tuple(getattr(record, record_attr) for record in records),
                legend_label=experiment_name,
                line_color=color,
            )
        plot.legend.location = legend_location
        plot.legend.click_policy = "hide"
        return plot

    x_by_nitd_plot_height = 300
    vacc_by_nitd_plot = plot_something_by_nitd(
        "val acc", vacc_range, "vacc", "bottom_right", x_by_nitd_plot_height
    )
    tracc_by_nitd_plot = plot_something_by_nitd(
        "train acc", tracc_range, "tracc", "bottom_right", x_by_nitd_plot_height
    )
    vmce_by_nitd_plot = plot_something_by_nitd(
        "val mean negative log likelihood",
        vmce_range,
        "vmce",
        "top_right",
        x_by_nitd_plot_height,
    )
    trmce_by_nitd_plot = plot_something_by_nitd(
        "train mean negative log likelihood",
        trmce_range,
        "trmce",
        "top_right",
        x_by_nitd_plot_height,
    )

    def create_range_slider(range: Range1d, title: str, step: float) -> RangeSlider:
        slider = RangeSlider(
            start=range.start,
            end=range.end,
            step=step,
            value=(range.bounds[0], range.bounds[1]),
            title=title,
        )
        slider.js_link("value", range, "start", attr_selector=0)
        slider.js_link("value", range, "end", attr_selector=1)
        return slider

    vmce_slider = create_range_slider(vmce_range, "val mean negative log likelihood", 0.05)
    trmce_slider = create_range_slider(trmce_range, "train mean negative log likelihood", 0.05)
    vacc_slider = create_range_slider(vacc_range, "val acc", 0.005)
    tracc_slider = create_range_slider(tracc_range, "train acc", 0.005)
    nitd_slider = create_range_slider(nitd_range, "number of iterations done", 10)

    div = Div(
        text=f'<p>{config["common_description"]}</p><ul style="list-style-type:circle;"><li>'
        + "</li><li>".join(
            f"<b>{name}</b>: <i>{description}</i> : {run_info}"
            for name, description, run_info in zip(
                experiments_names, experiments_descriptions, runs_infos
            )
        )
        + "</li></ul>"
    )

    if big_plots:
        p = gridplot(
            (
                (vacc_by_tracc_plot,),
                (div,),
                (vacc_slider,),
                (tracc_slider,),
                (vacc_by_nitd_plot,),
                (tracc_by_nitd_plot,),
                (vmce_slider,),
                (trmce_slider,),
                (nitd_slider,),
                (vmce_by_nitd_plot,),
                (trmce_by_nitd_plot,),
            )
        )
    else:
        p = gridplot(
            (
                (vacc_by_tracc_plot, div),
                (vacc_slider, tracc_slider),
                (vacc_by_nitd_plot, tracc_by_nitd_plot),
                (vmce_slider, trmce_slider),
                (nitd_slider,),
                (vmce_by_nitd_plot, trmce_by_nitd_plot),
            )
        )

    save(p)


if __name__ == "__main__":
    main()
