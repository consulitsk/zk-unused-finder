package com.example;

@interface Command {}

public class AdvancedViewModel {

    private User user = new User();

    public User getUser() {
        return user;
    }

    public String getDynamicValue(String key) {
        return "Value for " + key;
    }

    @Command
    public void runFromZscript() {
        System.out.println("This was triggered from a zscript block.");
    }
}
