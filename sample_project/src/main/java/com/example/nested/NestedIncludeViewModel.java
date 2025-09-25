package com.example.nested;

import org.zkoss.bind.annotation.Command;
import org.zkoss.bind.annotation.Init;

public class NestedIncludeViewModel {

    @Init
    public void init() {
        // init method
    }

    @Command
    public void doSomething() {
        System.out.println("This should be used.");
    }

    @Command
    public void unusedNestedMethod() {
        // This should be unused
    }
}