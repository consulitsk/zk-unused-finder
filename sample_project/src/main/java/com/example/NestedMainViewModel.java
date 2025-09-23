package com.example;

@interface Command {}

public class NestedMainViewModel {

    @Command
    public void saveAll() {
        System.out.println("Main VM saving all...");
    }

    public String getMainTitle() {
        return "Main View";
    }
}
