# Hardware/reference source intake — 2026-11-25

User-provided archives inspected without extraction or execution: SHA256 computed over exact uploaded bytes; ZIP central directories and root README inspected. Counts include directory entries. No omega_ontos/ or ontos_l12_config.json found in these six ZIPs. These are separate qualification inputs, not the missing v49 original 33-file source suite. Upstream revision, legal redistribution scope, complete CRC validation, dependency/build qualification and native execution remain OPEN. No binaries imported into Git.

| Archive | SHA256 | Entries | Declared expanded bytes | Intended mapping |
|---|---|---:|---:|---|
| LiteRT-main.zip | 25c268868268d4bbbf3977afc17aacb4820c1f6954b8ac3a7100168868f8cdcf | 9305 | 369267612 | Edge ML/GenAI runtime |
| gem5-stable.zip | 05c3ce3024ff3f72b826d17940c33cc01c291344bc0f10b1633357529964aa71 | 14192 | 113959830 | System and processor microarchitecture simulation |
| geniex-qairt-plugin-main.zip | 76411c71c444a72a9049e630c1608ef6f7e8852790076890075bef4907ee5577 | 596 | 650037571 | QAIRT Snapdragon NPU backend |
| kria-dfx-hw-xlnx_rel_v2022.1.zip | 78094ff948232ca1126bf4c61d78844418ad21d1a31c8098988ec5878d24fb45 | 675 | 45370124 | v67 Kria KV260/KR260 DFX reference designs |
| qai-appbuilder-main.zip | 740f129f820dce79346f3a7738eb269d6792a19a516cea81aabf5d7a381799d7 | 3887 | 74310891 | Qualcomm edge inference integration |
| ramulator2-main.zip | 2c37dbb31cb8aad81dace75781f6121daf6583e77a69a7eccd42d88996ee1174 | 556 | 2392196 | Ramulator 2.1 cycle-level DRAM model and gem5 integration |

## RAMXEED references

| Document | SHA256 |
|---|---|
| What_is_FeRAM_2409.pdf | a802507dd64ac872dd74710c3a44642dd8f1c3966a7119260f20fc7061f3ab5d |
| Introduction of FeRAM Usage_2409.pdf | f404fefbd490755af8ee0923ea77e454f637dbea499546dda75ca499354c6dee |
| RAMXEED's Philosophy System｜RAMXEED.pdf | d24f301347148fc9ffcfe2c96f1a24672828319c4853b5dec23549c34a6c5324 |
| Reasons to Choose FeRAM for Rotary Encoders｜RAMXEED.pdf | 3eb1e5603bc88a62371ee25069549097fd80e60066160d9a2214076f1af6f97a |

What is FeRAM pp. 5,10–13: product-family capacity/interface constraints and vendor example write cycle 120 ns, maximum endurance 10^14 cycles; 92% energy reduction only under stated 2 Mbit/3 V/SPI/2 KB/5 MHz/1 s conditions. Introduction p. 14 distinguishes example 150 ns power-loss diagram and headline 120 ns; do not merge into universal guarantee. Rotary encoder p. 3 describes MB85RDP16LX and 20–30 us supply windows for its internal counter use case; not a general-purpose atomic journal guarantee. Philosophy document is company context, not a timing specification. v69/v70 applicability requires actual part-level datasheet constraints and modeled power-loss/persistence behavior. FeRAM does not provide tamper-resistant anti-rollback by itself. Neither vendor claims nor source archives constitute executed hardware tests.
