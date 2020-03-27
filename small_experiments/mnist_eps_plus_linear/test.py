import pytorch_lightning as pl
from train import EPSPlusLinear

if __name__ == "__main__":
  model = EPSPlusLinear.load_from_metrics(
    "/mnt/important/experiments/eps_plus_linear_mnist/2020-03-26T23-18-59/lightning_logs/version_0/checkpoints/epoch=526.ckpt",
    "/mnt/important/experiments/eps_plus_linear_mnist/2020-03-26T23-18-59/lightning_logs/version_0/meta_tags.csv")
  trainer = pl.Trainer(logger=False, gpus=1)
  trainer = pl.Trainer(logger=False, gpus=1, checkpoint_callback=False)
  trainer.test(model)
