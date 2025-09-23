package com.example;

@interface Command {}

public class NestedDetailViewModel {

    @Command
    public void saveDetail() {
        System.out.println("Detail VM saving...");
    }

    public String getDetailInfo() {
        return "Some detail info.";
    }
}
