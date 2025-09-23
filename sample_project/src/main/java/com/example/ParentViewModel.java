package com.example;

@interface Command {}

public class ParentViewModel {

    public String getParentMessage() {
        return "Message from Parent";
    }

    @Command
    public void actionFromIncluded() {
        System.out.println("Action triggered from an included ZUL file.");
    }
}
