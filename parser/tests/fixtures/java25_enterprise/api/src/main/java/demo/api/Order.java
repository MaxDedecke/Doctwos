package demo.api;
import jakarta.xml.bind.annotation.*;
@XmlType(name="OrderType", namespace="urn:orders")
@XmlRootElement(name="submit", namespace="urn:orders")
@XmlAccessorType(XmlAccessType.FIELD)
public class Order {
    @XmlElement(name="id", namespace="urn:orders") public String id;
    @XmlTransient public String localOnly;
}
