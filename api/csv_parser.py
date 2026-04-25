"""
CSV parser for Mecalux warehouse challenge input files.

Parses the 4 CSV files (warehouse, obstacles, ceiling, types_of_bays)
into OptimizationInput model objects.
"""
from api_models import (
    WallPoint, Obstacle, CeilingPoint, BayType, OptimizationInput
)


def parse_warehouse_csv(content: str) -> list[WallPoint]:
    """
    Parse warehouse.csv: each line is 'x, y' defining a polygon vertex.
    Lines are ordered to form a closed polygon.
    """
    points = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            points.append(WallPoint(
                x=float(parts[0].strip()),
                y=float(parts[1].strip())
            ))
    return points


def parse_obstacles_csv(content: str) -> list[Obstacle]:
    """
    Parse obstacles.csv: each line is 'x, y, width, depth'.
    Empty file means no obstacles.
    """
    obstacles = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 4:
            obstacles.append(Obstacle(
                x=float(parts[0].strip()),
                y=float(parts[1].strip()),
                width=float(parts[2].strip()),
                depth=float(parts[3].strip())
            ))
    return obstacles


def parse_ceiling_csv(content: str) -> list[CeilingPoint]:
    """
    Parse ceiling.csv: each line is 'x, ceiling_height'.
    Defines a 1D height profile across the warehouse.
    """
    points = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            points.append(CeilingPoint(
                x=float(parts[0].strip()),
                height=float(parts[1].strip())
            ))
    return points


def parse_bay_types_csv(content: str) -> list[BayType]:
    """
    Parse types_of_bays.csv: each line is 'id, width, depth, height, gap, nLoads, price'.
    """
    bays = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 7:
            bays.append(BayType(
                id=int(parts[0].strip()),
                width=float(parts[1].strip()),
                depth=float(parts[2].strip()),
                height=float(parts[3].strip()),
                gap=float(parts[4].strip()),
                nLoads=int(parts[5].strip()),
                price=float(parts[6].strip())
            ))
    return bays


def parse_all(
    warehouse_csv: str,
    obstacles_csv: str,
    ceiling_csv: str,
    bay_types_csv: str,
) -> OptimizationInput:
    """Parse all 4 CSV strings into an OptimizationInput object."""
    return OptimizationInput(
        warehouse=parse_warehouse_csv(warehouse_csv),
        obstacles=parse_obstacles_csv(obstacles_csv),
        ceiling=parse_ceiling_csv(ceiling_csv),
        bay_types=parse_bay_types_csv(bay_types_csv),
    )
