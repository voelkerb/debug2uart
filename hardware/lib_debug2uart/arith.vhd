--------------------------------------------------------------------------------
-- File: arith.vhd
-- File history:
--
-- Description: 
--         required log2n to capture required bits to hold a given number.
--
-- Author: BV
--------------------------------------------------------------------------------

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_unsigned.all;
use work.interface_pkg.all;

package arith_pkg is
    -- return log2 of a given integer (will be rounded up)
    function log2n(n : integer) return integer; 
end package arith_pkg;

package body arith_pkg is
    function log2n(n : integer) return integer is
        variable temp : std_logic_vector(31 downto 0);
    begin
        temp := std_logic_vector(to_unsigned(n, 32));
        for i in 31 downto 1 loop
            if temp(i) = '1' then
                return i + 1;
            end if;
        end loop;
        return 1;
    end function;

end arith_pkg;