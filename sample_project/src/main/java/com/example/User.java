package com.example;

// A simple Java bean for testing complex EL expressions.
public class User {
    private String name = "Test User";
    private Address address = new Address();

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public static class Address {
        private String street = "123 Main St";

        public String getStreet() {
            return street;
        }
    }
}
