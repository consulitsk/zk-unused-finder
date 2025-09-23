package com.example;

public class OtherService {

    public void performAction() {
        UserViewModel vm = new UserViewModel();
        // This simulates a call from another part of the Java application.
        vm.processInternalData();
        vm.toOverride();
    }
}
