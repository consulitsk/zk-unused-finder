package com.example;

@interface GlobalCommand {}

public class GlobalCommandTestViewModel {
    @GlobalCommand
    public void aGlobalCommand() {
        // This should not be detected as unused because @GlobalCommand marks it as an entry point.
    }
}
