package demo.web;
import demo.api.Order;
import demo.api.Port;
import org.springframework.beans.factory.annotation.*;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/orders")
public class OrderController {
    @Autowired @Qualifier("fast") Port port;
    @Value("${orders.timeout:5}") int timeout;
    @Value("${orders.label}") String label;
    // tag::endpoint[]
    @PostMapping(consumes="application/json", produces="text/plain")
    public String create(@RequestBody Order order) { return port.submit(order); }
    // end::endpoint[]
}
