--------------------------------------------------------------------------------
-- File: inteface_pkg.vhd
-- File history:
--
-- Description: 
--         Module interface related type definitions and functions.
--
-- Author: BV
--------------------------------------------------------------------------------

library IEEE;
use IEEE.std_logic_1164.all;
package interface_pkg is
    constant TEST_DATA_WIDTH : natural := 32;
    constant TEST_SEL_WIDTH  : natural := 8;
    constant TEST_ADDR_WIDTH : natural := 8;

    -- array of a particular size of slv of a different size
    type test_array is array(natural range <>) of std_logic_vector;

    subtype test_sel_addr is std_logic_vector(TEST_SEL_WIDTH-1 downto 0);
    type test_sdi is record
        data_we  : std_logic;
        sel      : test_sel_addr;
        addr     : std_logic_vector(TEST_ADDR_WIDTH-1 downto 0);
        data_wr  : std_logic_vector(TEST_DATA_WIDTH-1 downto 0);
    end record;
    type test_sdo is record
        data_rd  : std_logic_vector(TEST_DATA_WIDTH-1 downto 0);
    end record;

end interface_pkg;