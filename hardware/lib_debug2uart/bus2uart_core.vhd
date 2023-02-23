--------------------------------------------------------------------------------
-- File: bus2uart_core.vhd
-- File history:
--
-- Description: 
--         Core of bus2uart debugging interface.
--
-- Author: BV
--------------------------------------------------------------------------------

library IEEE;

use IEEE.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;

library work;
use work.arith_pkg.all;
use work.interface_pkg.all;
use work.UART;

entity bus2uart_core is
    generic (
        CLK_FREQ : natural := 50e6;
        BAUD_RATE : natural := 115200;
        PARITY_BIT : string := "none"
    );
    port (
        clk   : in std_logic;
        reset : in std_logic;
        -- UART
        UART_RX  : in  std_logic;
        UART_TX  : out std_logic;
        -- BUS connect
        test_sdo : in  test_sdo;
        test_sdi : out test_sdi
    );
end bus2uart_core;

architecture behavior of bus2uart_core is

    type state_type is (IDLE, GET_SEL, GET_ADDR, CMD_WRITE, CMD_READ);
    signal state : state_type := IDLE;

    constant BYTE_PER_DATA : natural := integer(CEIL(REAL(TEST_DATA_WIDTH)/8.0));
    constant BYTE_PER_ADDR : natural := integer(CEIL(REAL(TEST_ADDR_WIDTH)/8.0));

    signal data_byte_cnt : unsigned(log2n(BYTE_PER_DATA-1)-1 downto 0);

    signal addr_byte_cnt : unsigned(log2n(BYTE_PER_ADDR-1)-1 downto 0);
    signal cmd, uart_rx_data, uart_tx_data : std_logic_vector(7 downto 0);

    signal addr_int : std_logic_vector((BYTE_PER_ADDR*8)-1 downto 0);
    signal sel_int : std_logic_vector(7 downto 0);
    
    -- signal data_out_int : std_logic_vector(DATA_WIDTH-1 downto 0);
    signal data_out_int : std_logic_vector(TEST_DATA_WIDTH-1 downto 0);
    
    signal uart_rx_valid, uart_tx_valid, uart_tx_rdy, uart_tx_rdy_bkp, data_wr_int : std_logic;
    signal data_in : std_logic_vector(TEST_DATA_WIDTH-1 downto 0);
    
    signal hello_cnt : unsigned(log2n(CLK_FREQ-1)-1 downto 0) := (others => '0');
begin

    -- Check that we can achieve a clean sampling frequency with the given dividers
    -- otherwise at least output a warning that sr is not perfect
    assert CEIL(REAL(TEST_DATA_WIDTH)/8.0) = FLOOR(REAL(TEST_DATA_WIDTH)/8.0)
    report "Data width must be multiple of 8"
        severity failure;

    test_sdi.addr <= addr_int(TEST_ADDR_WIDTH-1 downto 0);
    test_sdi.data_wr <= data_out_int;
    test_sdi.data_we <= data_wr_int;
    test_sdi.sel <= sel_int;
    data_in <= test_sdo.data_rd;

    FSM_PROC : process(clk, reset)
    begin
        if reset = '1' then
            state <= IDLE;
            data_byte_cnt <= (others => '0');
            addr_byte_cnt <= (others => '0');
            data_out_int <= (others => '0');
            data_wr_int <= '0';
            addr_int <= (others => '0');
            cmd <= (others => '0');
            uart_tx_valid <= '0';
            uart_tx_data <= (others => '0');
            hello_cnt <= (others => '0');
            uart_tx_rdy_bkp <= '0';

        elsif rising_edge(clk) then
            -- stay in state
            state <= state;
            -- Standard values
            uart_tx_valid <= '0';
            data_wr_int <= '0';

            -- 100ms timeout
            if hello_cnt > integer(CLK_FREQ*0.1)-1 then
                state <= IDLE;
            end if;
            
            if hello_cnt >= CLK_FREQ-1 then
                hello_cnt <= (others => '0');
            else             
                hello_cnt <= hello_cnt + 1;
            end if;
            
            -- Unfortunately uart tx rdy is more than one clock cycle high, so we need
            -- to make sure that we at least see a 0 here again.
            -- Make sure to only transition forward if uart_tx_rdy = '1' and uart_tx_rdy_bkp = '0'
            if uart_tx_rdy = '0' then 
                uart_tx_rdy_bkp <= '0';
            end if;
            -- waiting for command
            if state = IDLE then
                -- capture command
                cmd <= uart_rx_data;
                -- addr counter is 0
                addr_byte_cnt <= (others => '0');
                data_byte_cnt <= (others => '0');
                -- On incoming data, go to addr read state
                if uart_rx_valid = '1' then
                    -- Hello request
                    if uart_rx_data = x"fe" then
                        -- Send response
                        if (uart_tx_rdy = '1' and uart_tx_rdy_bkp = '0') then
                            uart_tx_rdy_bkp <= uart_tx_rdy;
                            uart_tx_valid <= '1';
                            uart_tx_data <= x"fe";
                        end if;
                    -- valid request
                    elsif uart_rx_data = x"00" or uart_rx_data = x"01" then
                        state <= GET_SEL;
                        hello_cnt <= (others => '0');
                    -- Invalid request
                    else 
                        -- Send error
                        if (uart_tx_rdy = '1' and uart_tx_rdy_bkp = '0') then
                            uart_tx_rdy_bkp <= uart_tx_rdy;
                            uart_tx_valid <= '1';
                            uart_tx_data <= x"30";
                        end if;
                    end if;
                end if;


            -- capture address request
            elsif state = GET_SEL then
                 -- On new data
                 if uart_rx_valid = '1' then
                    -- construct addr word
                    sel_int <= uart_rx_data;
                    state <= GET_ADDR;
                end if;

            -- capture address request
            elsif state = GET_ADDR then
                -- On new data
                if uart_rx_valid = '1' then
                    -- construct addr word
                    addr_int(to_integer((addr_byte_cnt+1))*8-1 downto to_integer(addr_byte_cnt)*8) <= uart_rx_data;
                    -- If all address bytes caputres, go to read or write state depending on cmd
                    if addr_byte_cnt >= BYTE_PER_ADDR-1 then
                        -- WR cmd is decided upon first bit
                        if cmd(0) = '1' then
                            state <= CMD_WRITE;
                        else
                            state <= CMD_READ;
                        end if;
                    -- Increment byte counter
                    else 
                        addr_byte_cnt <= addr_byte_cnt + 1;
                    end if;
                end if;

            -- capture address request
            elsif state = CMD_WRITE then
                -- On new data
                if uart_rx_valid = '1' then
                    -- construct data word
                    data_out_int(to_integer((data_byte_cnt+1))*8-1 downto to_integer(data_byte_cnt)*8) <= uart_rx_data;
                    -- If all data bytes caputred, write to ram and go back to idle
                    if data_byte_cnt >= BYTE_PER_DATA-1 then
                        state <= IDLE;
                        data_wr_int <= '1';
                    -- Increment byte counter
                    else 
                        data_byte_cnt <= data_byte_cnt + 1;
                    end if;
                end if;

            -- capture address request
            elsif state = CMD_READ then
                if uart_tx_rdy = '1' and uart_tx_rdy_bkp = '0' then
                    uart_tx_rdy_bkp <= uart_tx_rdy;

                    uart_tx_valid <= '1';
                    -- if unsigned(addr_int) > 2**ADDR_WIDTH-1 then
                    if unsigned(addr_int) > 2**TEST_ADDR_WIDTH-1 then
                        uart_tx_data <= (others => '0');
                    else 
                        -- if data_byte_cnt = 0 then
                        --     uart_tx_data <= data_in(7 downto 0);
                        -- elsif data_byte_cnt = 1 then
                        --     uart_tx_data <= data_in(15 downto 8);
                        -- elsif data_byte_cnt = 2 then
                        --     uart_tx_data <= data_in(23 downto 16);
                        -- elsif data_byte_cnt = 3 then
                        --     uart_tx_data <= data_in(31 downto 24);
                        -- end if; 
                        -- uart_tx_data <= std_logic_vector(to_unsigned(to_integer(data_byte_cnt), 8));
                        uart_tx_data <= data_in(to_integer((data_byte_cnt+1))*8-1 downto to_integer(data_byte_cnt)*8);
                    end if;
                    -- If all address bytes caputres, go to read or write state depending on cmd
                    if data_byte_cnt >= BYTE_PER_DATA-1 then
                        state <= IDLE;
                    else 
                        data_byte_cnt <= data_byte_cnt + 1;
                    end if;
                end if;
            end if;
        end if;
    end process;


	uart_i: entity work.UART
        generic map (
            CLK_FREQ      => CLK_FREQ,
            BAUD_RATE     => BAUD_RATE,
            PARITY_BIT    => PARITY_BIT,
            USE_DEBOUNCER => True
        )
        port map (
            CLK          => clk,
            RST          => reset,
            -- UART INTERFACE
            UART_TXD     => UART_TX,
            UART_RXD     => UART_RX,
            -- USER DATA INPUT INTERFACE
            DIN          => uart_tx_data,
            DIN_VLD      => uart_tx_valid,
            DIN_RDY      => uart_tx_rdy,
            -- USER DATA OUTPUT INTERFACE
            DOUT         => uart_rx_data,
            DOUT_VLD     => uart_rx_valid,
            FRAME_ERROR  => open,
            PARITY_ERROR => open
        );

end behavior;
