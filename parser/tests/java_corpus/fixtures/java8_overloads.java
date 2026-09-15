package corpus.legacy;

import java.util.List;

@Deprecated
public class Catalog<T extends Number> {
    private final List<T> values;
    int count, limit;

    public Catalog(List<T> values) {
        this.values = values;
    }

    public T find(int index) {
        return values.get(index);
    }

    public T find(String key) {
        return values.get(key.length());
    }

    public static class Entry {
        String key;
    }
}
