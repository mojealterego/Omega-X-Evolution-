// Static shell model. The verify-input MUST originate from an external TCB.
// This module is not a cryptographic signature checker or physical DFX controller.
// The 256-bit expected shell digest is a build parameter, not a mutable register.
`timescale 1ns/1ps
module ontos_static_shell_v67 #(
    parameter logic [255:0] EXPECTED_SHELL_SHA256 =
      256'h3c6e0b8a9f5d416c2e8a112c50352a729ae5a7a4b927a4c09f67a38b6db54981
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         operator_recover,
    input  logic         dfx_swap_request,
    input  logic         signed_receipt_valid,
    input  logic [255:0] observed_shell_sha256,
    input  logic         gsai_veto,
    input  logic         energy_fault,
    output logic         dfx_decouple,
    output logic         icap_write_en,
    output logic         lockdown_out
);
    typedef enum logic [1:0] {
        ST_LOCKDOWN=2'b00, ST_READY=2'b01,
        ST_DECOUPLED=2'b10, ST_PROGRAM=2'b11
    } shell_state_t;
    shell_state_t state_q, state_d;
    logic attested;
    assign attested = signed_receipt_valid &&
                      observed_shell_sha256 == EXPECTED_SHELL_SHA256;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) state_q <= ST_LOCKDOWN;
        else state_q <= state_d;
    end
    always_comb begin
        state_d = state_q;
        dfx_decouple = 1'b1;
        icap_write_en = 1'b0;
        lockdown_out = 1'b0;
        if (gsai_veto || energy_fault) begin
            state_d = ST_LOCKDOWN;
        end else begin
            case (state_q)
                ST_LOCKDOWN: begin
                    if (operator_recover && attested) state_d = ST_READY;
                end
                ST_READY: begin
                    dfx_decouple = 1'b0;
                    if (dfx_swap_request) begin
                        if (attested) state_d = ST_DECOUPLED;
                        else state_d = ST_LOCKDOWN;
                    end
                end
                ST_DECOUPLED: begin
                    if (attested) state_d = ST_PROGRAM;
                    else state_d = ST_LOCKDOWN;
                end
                ST_PROGRAM: begin
                    if (attested && dfx_swap_request) icap_write_en = 1'b1;
                    else state_d = ST_LOCKDOWN;
                end
                default: state_d = ST_LOCKDOWN;
            endcase
        end
        lockdown_out = (state_d == ST_LOCKDOWN);
        if (state_d == ST_LOCKDOWN) begin
            icap_write_en = 1'b0;
            dfx_decouple = 1'b1;
        end
    end
endmodule
