from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import shape
from shapely.validation import explain_validity

from farm_common.errors import AppError
from land_service.schemas import Point, Polygon


def polygon_to_db(boundary: Polygon):
    polygon = shape(boundary.model_dump())
    if not polygon.is_valid:
        raise AppError("INVALID_PLOT_BOUNDARY", explain_validity(polygon), 422)
    if polygon.area <= 0:
        raise AppError("INVALID_PLOT_BOUNDARY", "Plot boundary must have positive area", 422)
    return from_shape(polygon, srid=4326)


def point_to_db(point: Point):
    lng, lat = point.coordinates
    return from_shape(ShapelyPoint(lng, lat), srid=4326)


def geometry_json(value):
    return to_shape(value).__geo_interface__
