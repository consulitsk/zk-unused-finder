package com.example;

public class CompletelyUnusedViewModel {

    private String message;

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public void doNothing() {
        // This should be reported as unused.
    }
}
