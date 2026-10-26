package demo.impl;
import demo.api.Order;
import demo.api.Port;
import org.springframework.stereotype.Service;
@Service("fast")
public class Fast implements Port {
    public String submit(Order order) { return "fast"; }
}
