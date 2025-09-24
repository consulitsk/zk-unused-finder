package com.example;

@interface Command {}

public class DynamicIncludeViewModel {
    public String getPath() {
        return "some_dynamic_path";
    }

    @Command
    public void commandInDynamicA() {}

    @Command
    public void commandInDynamicB() {}
}
