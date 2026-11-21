// DFX partition reference, Q16.16, no external ICAP/write interface.
// Arithmetic checked against a separately compiled native C + WASM model;
// actual RTL simulation/synthesis is NOT certified without HDL tooling.
`timescale 1ns/1ps
module ontos_q16_core_v67 (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               decouple_in,
    input  logic               valid_in,
    input  logic signed [31:0] mu_in,
    input  logic signed [31:0] drive_in,
    input  logic signed [31:0] decay_q16,
    output logic               valid_out,
    output logic signed [31:0] mu_out
);
    localparam logic signed [31:0] ONE_Q16 = 32'sd65536;
    logic signed [31:0] one_minus_d;
    logic signed [63:0] prod_drive;
    logic signed [63:0] prod_mu;
    logic signed [31:0] blended;
    always_comb begin
        one_minus_d = ONE_Q16 - decay_q16;
        prod_drive  = $signed(decay_q16) * $signed(drive_in);
        prod_mu     = $signed(one_minus_d) * $signed(mu_in);
        blended     = $signed(prod_drive >>> 16) + $signed(prod_mu >>> 16);
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_out <= 1'b0;
            mu_out <= 32'sd0;
        end else if (decouple_in) begin
            valid_out <= 1'b0;
            mu_out <= 32'sd0;
        end else begin
            valid_out <= valid_in;
            if (valid_in) mu_out <= blended;
        end
    end
endmodule
