--------------------------------------------------------------------------------
-- File: example_top_level.vhd
-- File history:
--
-- Description: 
--         Example on how to use the bus2uart interface.
--
-- Author: BV
--------------------------------------------------------------------------------

library IEEE;

use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use ieee.math_real.all;

library lib_debug2uart;
use lib_debug2uart.interface_pkg.all;
use lib_debug2uart.arith_pkg.log2n;

entity delay is
    generic (
        clk_frequency : natural := 25000000;
        delay_us      : natural := 1000000;
        polarity      : std_logic := '1'
    );
    port (
        clk   : in  std_logic; -- example
        reset : in  std_logic;
        fire  : out std_logic;
        -- test interface
        test_sel_addr : in  test_sel_addr;
        test_sdi      : in  test_sdi;
        test_sdo      : out test_sdo
    );
end delay;
architecture architecture_delay of delay is
    
    -- clks to accomodate 1us
    constant VAL_1US : natural := clk_frequency/1000000;
    -- max value required
    constant CNT_MAX : natural := VAL_1US * delay_us;
    -- bit width required
    constant CNT_WIDTH : integer := log2n(CNT_MAX);
    -- counter
    signal cnt : unsigned(CNT_WIDTH - 1 downto 0) := (others => '0');

    -- TEST interface
    signal test_read_data_int : std_logic_vector(31 downto 0);

begin

    -- Check that clk frequency allows to count to one full us
    assert (clk_frequency >= 1000000) and (CEIL(REAL(clk_frequency)/1000000.0) = FLOOR(REAL(clk_frequency)/1000000.0))
    report "Input clk freq should be an integer multiple of 1MHz"
    severity error;
    
    process (clk, reset)
    begin
        if rising_edge(clk) then
            if reset = '1' then
                fire <= not polarity;
                cnt <= (others => '0');
            else 
                if cnt >= CNT_MAX then
                    fire <= polarity;
                    cnt <= (others => '1');
                else
                    cnt <= cnt + 1;
                    fire <= not polarity;
                end if;
            end if;
        end if;
    end process;

    -- Test interface
    test_sdo.data_rd <= test_read_data_int when test_sdi.sel = test_sel_addr else (others => 'Z');

    TEST_PROC : process(test_sdi.addr)
    begin
        test_read_data_int <= (others => '0');
        case test_sdi.addr is
            when x"00"  => test_read_data_int(cnt'left downto 0) <= std_logic_vector(cnt);
            when x"01"  => test_read_data_int <= std_logic_vector(to_unsigned(CNT_MAX, test_read_data_int'length));
            when x"02"  => test_read_data_int <= (others => fire);
            when others => test_read_data_int(7 downto 0) <= x"fe";
        end case;
    end process;

    
end architecture_delay;

library IEEE;

use IEEE.std_logic_1164.all;
use ieee.numeric_std.all;
library work;


library lib_debug2uart;
use lib_debug2uart.all;
use lib_debug2uart.interface_pkg.all;
use lib_debug2uart.arith_pkg.log2n;
use lib_debug2uart.debug2uart_register;
use lib_debug2uart.bus2uart_core;

entity top_level is
    generic (
        CLK_FREQ : natural := 50e6
    );
    port (
        clk     : in std_logic;
        reset   : in std_logic;
        BTNs    : in std_logic_vector(7 downto 0);
        LEDs    : out std_logic_vector(7 downto 0);
        -- Test UART
        UART_RX : in std_logic;
        UART_TX : out std_logic
    );
end top_level;
architecture behavior of top_level is
    type counter_array is array(natural range <>) of unsigned;

    constant MAX_COUNT : natural := 5000;
    signal counters : counter_array(7 downto 0)(log2n(MAX_COUNT)-1 downto 0) := (others => (others => '0'));

    constant MAX_COUNT_MS : natural := CLK_FREQ/1000;
    signal ms_counter : unsigned(log2n(MAX_COUNT_MS)-1 downto 0) := (others => '0');
    signal cnt_clk, cnt_bkp : std_logic := '0';

    signal LEDs_int : std_logic_vector(7 downto 0) := (others => '0');

    -- TEST interface
    constant TEST_BAUDRATE : natural := 115200;
    signal test_sdi : test_sdi;
    signal test_sdo : test_sdo;
    signal test_read_data_int : std_logic_vector(31 downto 0);
begin
    

    delay_i: entity work.delay
        generic map (
            clk_frequency => CLK_FREQ,
            delay_us      => 1000,
            polarity      => '1'
        )
        port map (
            clk   => clk,
            reset => (cnt_clk or reset), -- Resetting itself (1 for 1 clk cycle)
            fire  => cnt_clk,
            -- test interface
            test_sel_addr => x"01",
            test_sdi      => test_sdi,
            test_sdo      => test_sdo
        );


    FSM_PROC : process(clk, reset, cnt_clk)
    begin
        if rising_edge(clk) then
            if reset = '1' then
                LEDs_int <= (others => '0');
                counters <= (others => (others => '0'));
            else
                if cnt_clk = '1' then
                    for i in 0 to 7 loop
                        if counters(i) >= 4000 then
                            LEDs_int(i) <= '1';
                        else
                            LEDs_int(i) <= '0';
                        end if;

                        if counters(i) >= MAX_COUNT then
                            counters(i) <= (others => '0');
                        else
                            counters(i) <= counters(i) + 1;
                        end if;
                        
                    end loop;
                end if;
            end if;
        end if;
    end process;
    
    LEDs <= LEDs_int;


    -- Test interface
    test_sdo.data_rd <= test_read_data_int when test_sdi.sel = x"00" else (others => 'Z');

    TEST_PROC : process(test_sdi.addr)
    begin
        test_read_data_int <= (others => '0');
        case test_sdi.addr is
            when x"00"  => test_read_data_int(counters(0)'left downto 0) <= std_logic_vector(counters(0));
            when x"01"  => test_read_data_int(counters(1)'left downto 0) <= std_logic_vector(counters(1));
            when x"02"  => test_read_data_int(counters(2)'left downto 0) <= std_logic_vector(counters(2));
            when x"03"  => test_read_data_int(counters(3)'left downto 0) <= std_logic_vector(counters(3));
            when x"04"  => test_read_data_int(counters(4)'left downto 0) <= std_logic_vector(counters(4));
            when x"05"  => test_read_data_int(counters(5)'left downto 0) <= std_logic_vector(counters(5));
            when x"06"  => test_read_data_int(counters(6)'left downto 0) <= std_logic_vector(counters(6));
            when x"07"  => test_read_data_int(counters(7)'left downto 0) <= std_logic_vector(counters(7));
            when x"08"  => test_read_data_int(BTNs'left downto 0) <= BTNs;
            when x"09"  => test_read_data_int(LEDs'left downto 0) <= LEDs;
            when others => test_read_data_int(7 downto 0) <= x"fe";
        end case;
    end process;

    
    TEST_I : entity lib_debug2uart.bus2uart_core
        generic map (
            CLK_FREQ   => CLK_FREQ,
            BAUD_RATE  => TEST_BAUDRATE
        )
        port map (
            clk     => clk,
            reset   => reset,
            UART_TX => UART_TX,
            UART_RX => UART_RX,
            -- Test interface
            test_sdi => test_sdi,
            test_sdo => test_sdo
        );

end behavior;


