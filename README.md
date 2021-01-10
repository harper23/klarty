# Kingst Logic Analyser Research Tool for You

Python tool for experimenting with the Kingst LA1016 / LA2016 16-channel logic analysers, as shown here https://sigrok.org/wiki/Kingst_LA2016

The main components of the LA are:

- Cypress FX2 80c51 Microcontroller with High Speed 480Mb/s USB interface
- EEPROM for FX2 configuration
- Cyclone 4 FPGA
- 128MByte SDRAM
- Dual Op-Amp PWM DAC for input threshold adjustment
- Unbranded IC for device authentication (SOIC8 adjacent to the LED), probably a small microcontroller. No impact on PV integration, ignore it.

Very quick summary of operation:

- The FX2 firmware and FPGA bitstream are loaded from the PC before use.
- The FX2 sends the bitstream to the FPGA using sync serial connection (EP2 > SCON0), Altera passive serial config mode.
- The FPGA stores samples in the SDRAM as repetition packets; 16bit inputs plus one byte repeat count.
- To facilitate fast data upload the FPGA reads data from the SDRAM and passes it to the FX2 GPIF interface (FPGA > EP86).

- The FPGA has approximately 60 byte-wide registers accessed via SPI (FX2 is master) to control sampling and data upload.
- The FPGA registers have an address range of 0x00 to 0x7F, most are write only and just read as zero.
- To read a register, the top bit of the address is set high. For write it is low.
- 0x80 means read register 0x00. 0x90 means read register 0x10.
- This may have caused some confusion as the FPGA register addresses are wrong in PV.
- Alternatively, the OEM may have changed the fw and bitstream.

Most of the code is in klarty.py while the other python files labelled 1,2,3 should be run
in that order to program the FX2, FPGA and run the analyser.
Firmware files are not included, they will need extracted from OEM software.
The python files and OEM software used for testing are archived here:

https://bitbucket.org/magellanic-clouds/

The python script from extracting firmware and bitsteam are linked on this page:

https://sigrok.org/wiki/Kingst_LA2016

The extracted FX2 firmware functions OK.
However, in my experience, the extracted FPGA bitstream does not operate correctly.
A bitstream extracted from OEM software USB communication packets did work correctly.