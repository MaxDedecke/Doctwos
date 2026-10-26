package demo.soap;
import demo.api.Order;
import jakarta.jws.*;
@WebService(name="OrdersPort", targetNamespace="urn:orders", serviceName="Orders")
public class OrdersEndpoint {
    @WebMethod(operationName="submit")
    public String submit(Order order) { return order.id; }
}
