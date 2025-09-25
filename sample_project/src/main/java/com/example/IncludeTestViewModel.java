package com.example;

@interface Command {}

public class IncludeTestViewModel {
    @Command
    public void commandInMain() {}

    @Command
    public void commandInRelative() {}

    @Command
    public void commandInAbsolute() {}
}
