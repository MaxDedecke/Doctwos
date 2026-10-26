package demo.impl;
import demo.api.Order;
import demo.api.Port;
import org.springframework.stereotype.Service;
@Service("slow")
public class Slow implements Port {
    public String submit(Order order) { return "slow"; }
}
