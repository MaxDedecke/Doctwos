package corpus.lombok;

import lombok.Data;
import lombok.Getter;
import lombok.Setter;

@Data
public class Customer {
    private String name;
    private final int id;
    @Getter(AccessLevel.NONE)
    private String internalCode;
}

class Flags {
    @Getter @Setter
    boolean isEnabled;
    public boolean isEnabled() { return isEnabled; }
}
