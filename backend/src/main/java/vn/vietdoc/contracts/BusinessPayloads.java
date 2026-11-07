package vn.vietdoc.contracts;

import java.util.List;

/** Typed DTOs for the stable business payloads shared by review, extraction and export. */
public final class BusinessPayloads {
  private BusinessPayloads() {}

  public sealed interface Payload permits Receipt, Invoice {
    List<LineItem> items();
  }

  public record LineItem(
      String description, String quantity, String unit, String unit_price, String line_total) {}

  public record Receipt(
      String merchant_name,
      String merchant_address,
      String transaction_date,
      String transaction_time,
      String total_amount,
      List<LineItem> items)
      implements Payload {}

  public record Invoice(
      String invoice_number,
      String issue_date,
      String seller_name,
      String buyer_name,
      String subtotal,
      String tax_amount,
      String discount_amount,
      String total_amount,
      List<LineItem> items)
      implements Payload {}
}
