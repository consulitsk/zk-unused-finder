package com.example;

// A base class for other ViewModels to extend.
public abstract class BaseViewModel {

    // A method that might be used by subclasses.
    public void commonBaseFunction() {
        System.out.println("Executing common function from BaseViewModel.");
    }

    // A method that will be overridden.
    public void toOverride() {
        System.out.println("Base toOverride");
    }
}
