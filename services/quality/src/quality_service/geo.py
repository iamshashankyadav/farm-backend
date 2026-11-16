from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point as ShapelyPoint

from quality_service.schemas import Point


def point_to_db(point: Point):
    lng, lat = point.coordinates
    return from_shape(ShapelyPoint(lng, lat), srid=4326)


def point_json(value):
    if value is None:
        return None
    return to_shape(value).__geo_interface__
