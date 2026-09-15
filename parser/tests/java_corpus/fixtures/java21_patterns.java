package corpus.modern;

sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

final class Area {
    static double calculate(Shape shape) {
        return switch (shape) {
            case Circle circle when circle.radius() > 0 -> Math.PI * circle.radius() * circle.radius();
            case Rectangle(double width, double height) -> width * height;
        };
    }
}
