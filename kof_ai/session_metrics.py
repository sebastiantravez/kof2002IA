"""Una sola instantánea para el resumen de terminal y el JSON de sesión."""


def snapshot(defense, brain, rounds):
    metrics = defense.metrics(rounds)
    metrics["fuente_danio"] = "DefenseLogger"
    metrics["danio_recibido_golpes"] = metrics["danio_recibido"] - metrics["danio_raspado"]
    metrics["diagnostico_cerebro"] = {
        "danio_hecho": brain.dealt_total,
        "danio_recibido_golpes": brain.taken_total,
        "danio_raspado": brain.chip_total,
        "danio_recibido_total": brain.taken_total + brain.chip_total,
    }
    metrics["diferencia_logger_cerebro"] = {
        "danio_hecho": metrics["danio_hecho"] - brain.dealt_total,
        "danio_recibido_total": metrics["danio_recibido"] - brain.taken_total - brain.chip_total,
    }
    return metrics


def damage_line(metrics):
    return (f"Danio hecho {metrics['danio_hecho']}, recibido {metrics['danio_recibido']} total "
            f"({metrics['danio_recibido_golpes']} en golpes + "
            f"{metrics['danio_raspado']} de raspado bloqueando especiales)")
