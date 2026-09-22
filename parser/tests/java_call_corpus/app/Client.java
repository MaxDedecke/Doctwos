package app;

import api.Base;
import api.Service;
import static api.Util.check;

class Client extends Base {
    Service service;

    void run(Service parameter) {
        parameter.run();
        service.run();
        check(1);
        super.inherited();
        Missing.execute();
    }
}
