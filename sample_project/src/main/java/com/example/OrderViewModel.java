package com.example;

// Dummy annotations
@interface Command {
    String value() default "";
}
@interface GlobalCommand {
    String value() default "";
}

public class OrderViewModel extends BaseViewModel {

    private String orderId;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    @Command("submitOrder")
    public void doSubmit() {
        // This command has an explicit name.
        System.out.println("Order submitted: " + orderId);
    }

    @GlobalCommand("refreshOrders")
    public void refresh() {
        // This is a global command.
        System.out.println("Refreshing all orders.");
    }
}
