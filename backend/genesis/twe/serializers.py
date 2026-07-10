from datetime import datetime


def iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def duration_seconds(row):
    start = row.get("started_at")
    end = row.get("completed_at")
    if not start or not end:
        return None
    return int((end - start).total_seconds())


def operation_summary(row):
    return {
        "id": str(row["id"]),
        "instance_id": str(row["game_instance_id"]),
        "capability": row["capability"],
        "status": row["status"],
        "current_stage": row["current_stage"],
        "requested_at": iso(row["requested_at"]),
        "started_at": iso(row["started_at"]),
        "completed_at": iso(row["completed_at"]),
        "result_message": row["result_message"],
    }


def operation_with_requester(row):
    data = operation_summary(row)
    data["requested_by"] = {
        "id": str(row["requested_by"]),
        "display_name": row["requested_by_display_name"],
    }
    data["duration_seconds"] = duration_seconds(row)
    return data
