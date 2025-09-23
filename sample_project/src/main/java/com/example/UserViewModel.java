package com.example;

// Dummy annotations to make the example parsable
@interface Init {}
@interface Command {}
@interface NotifyChange {}

public class UserViewModel extends BaseViewModel {

    private String username;

    @Init
    public void init() {
        // This method is called by the ZK framework and should not be marked as unused.
        this.username = "JohnDoe";
    }

    public String getUsername() {
        return username;
    }

    @NotifyChange("username")
    public void setUsername(String username) {
        this.username = username;
    }

    @Command
    public void saveUser() {
        // This method is triggered by a @command in the ZUL file.
        System.out.println("User saved: " + this.username);
    }

    public void processInternalData() {
        // This method is called by another service/class within the Java code.
        System.out.println("Processing some internal data.");
    }

    public void unusedMethod() {
        // This method is not used anywhere and should be detected by the tool.
        System.out.println("This should not be called.");
    }

    @Override
    public void toOverride() {
        System.out.println("UserViewModel toOverride");
    }
}
