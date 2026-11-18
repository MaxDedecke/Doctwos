package corpus.records;

record Point(double x, double y) {
    double distanceTo(Point other) {
        return Math.hypot(x - other.x(), y - other.y());
    }
}

record Line(Point start, Point end) {}

record Box(Object content, Object label) {}

final class Geometry {
    static double length(Object value) {
        return switch (value) {
            case Line(var start, var end) -> start.distanceTo(end);
            case Box(Line(Point(var x, var y), _), _) -> x + y;
            default -> 0;
        };
    }

    static double width(Object value) {
        if (value instanceof Line(final var start, Point end)) {
            return end.x() - start.x();
        }
        switch (value) {
            case Box(var content, _):
                return content.hashCode();
            default:
                return 0;
        }
    }

    static int after() {
        return 1;
    }
}
