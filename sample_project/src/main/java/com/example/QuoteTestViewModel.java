package com.example;

@interface Command {}

public class QuoteTestViewModel {
    @Command
    public void aCommandWithDoubleClick() {
        // This should be detected as used from quotetest.zul
    }

    @Command
    public void anUnusedCommand() {
        // This should be detected as unused
    }
}
