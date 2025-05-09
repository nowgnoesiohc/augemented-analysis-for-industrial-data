import argparse
import traceback
import pytorch_lightning as pl
from pytorch_lightning.utilities import rank_zero_info
import models
import tasks
import utils.callbacks
import utils.data
import utils.email
import utils.logging


DATA_PATHS = {
    "bay_0": {"feat": "data/bay/speed_bay_0.csv", "adj": "data/bay/adj_mx_bay.csv"},
    "bay_5": {"feat": "data/bay/speed_bay_5.csv", "adj": "data/bay/adj_mx_bay.csv"},
    "bay_10": {"feat": "data/bay/speed_bay_10.csv", "adj": "data/bay/adj_mx_bay.csv"},
    "bay_20": {"feat": "data/bay/speed_bay_20.csv", "adj": "data/bay/adj_mx_bay.csv"},
    "la_0": {"feat": "data/la/speed_la_0.csv", "adj": "data/la/adj_mx_la.csv"},
    "la_5": {"feat": "data/la/speed_la_5.csv", "adj": "data/la/adj_mx_la.csv"},
    "la_10": {"feat": "data/la/speed_la_10.csv", "adj": "data/la/adj_mx_la.csv"},
    "la_20": {"feat": "data/la/speed_la_20.csv", "adj": "data/la/adj_mx_la.csv"},
    "gang_0": {"feat": "data/gangnam/speed_gangnam_0.csv", "adj": "data/gangnam/adj_mx_gangnam.csv"},
    "gang_5": {"feat": "data/gangnam/speed_gangnam_5.csv", "adj": "data/gangnam/adj_mx_gangnam.csv"},
    "gang_10": {"feat": "data/gangnam/speed_gangnam_10.csv", "adj": "data/gangnam/adj_mx_gangnam.csv"},
    "gang_20": {"feat": "data/gangnam/speed_gangnam_20.csv", "adj": "data/gangnam/adj_mx_gangnam.csv"}
}


def get_model(args, dm):
    model = None
    if args.model_name == "GCN":
        model = models.GCN(adj=dm.adj, input_dim=args.seq_len, output_dim=args.hidden_dim)
    if args.model_name == "TGCN":
        model = models.TGCN(adj=dm.adj, hidden_dim=args.hidden_dim)
    return model


def get_task(args, model, dm):
    task = getattr(tasks, args.settings.capitalize() + "ForecastTask")(
        model=model, feat_max_val=dm.feat_max_val, **vars(args)
    )
    return task


def get_callbacks(args):
    checkpoint_callback = pl.callbacks.ModelCheckpoint(monitor="train_loss")
    plot_validation_predictions_callback = utils.callbacks.PlotValidationPredictionsCallback(monitor="train_loss")
    callbacks = [
        checkpoint_callback,
        plot_validation_predictions_callback,
    ]
    return callbacks


def main_supervised(args):
    dm = utils.data.SpatioTemporalCSVDataModule(
        feat_path=DATA_PATHS[args.data]["feat"], adj_path=DATA_PATHS[args.data]["adj"], **vars(args)
    )
    model = get_model(args, dm)
    task = get_task(args, model, dm)
    callbacks = get_callbacks(args)
    trainer = pl.Trainer.from_argparse_args(args, callbacks=callbacks)
    trainer.fit(task, dm)
    results = trainer.validate(datamodule=dm)
    return results


def main(args):
    rank_zero_info(vars(args))
    results = globals()["main_" + args.settings](args)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser = pl.Trainer.add_argparse_args(parser)

    parser.add_argument(
        "--data", type=str, help="The name of the dataset", default="bay_0"
    )
    parser.add_argument(
        "--model_name",
        type=str,
        help="The name of the model for spatiotemporal prediction",
        choices=("GCN", "GRU", "TGCN"),
        default="GCN",
    )
    parser.add_argument(
        "--settings",
        type=str,
        help="The type of settings, e.g. supervised learning",
        choices=("supervised",),
        default="supervised",
    )
    parser.add_argument("--log_path", type=str, default=None, help="Path to the output console log file")
    parser.add_argument("--send_email", "--email", action="store_false", help="Send email when finished")

    temp_args, _ = parser.parse_known_args()

    parser = getattr(utils.data, temp_args.settings.capitalize() + "DataModule").add_data_specific_arguments(parser)
    parser = getattr(models, temp_args.model_name).add_model_specific_arguments(parser)
    parser = getattr(tasks, temp_args.settings.capitalize() + "ForecastTask").add_task_specific_arguments(parser)

    args = parser.parse_args()
    utils.logging.format_logger(pl._logger)
    if args.log_path is not None:
        utils.logging.output_logger_to_file(pl._logger, args.log_path)

    try:
        results = main(args)
    except:  # noqa: E722
        traceback.print_exc()
        if args.send_email:
            tb = traceback.format_exc()
            subject = "[Email Bot][❌] " + "-".join([args.settings, args.model_name, args.data])
            utils.email.send_email(tb, subject)
        exit(-1)

    if args.send_email:
        subject = "[Email Bot][✅] " + "-".join([args.settings, args.model_name, args.data])
        utils.email.send_experiment_results_email(args, results, subject=subject)
