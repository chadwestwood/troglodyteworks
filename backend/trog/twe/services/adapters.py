from . import local_asa


def adapter_for(name: str):
    if name == "local_asa":
        return local_asa
    return None
