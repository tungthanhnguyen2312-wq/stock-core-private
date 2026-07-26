# Risk, Liquidity & Backtesting Contract

Schema/method version `1.0.0`. Realized/downside volatility use simple consecutive adjusted-price returns; drawdown is running-peak drawdown. Inputs require qualified adjustment semantics, common valid sessions, and no forward-filled returns. Volume requires qualified units; zero volume remains an explicit illiquidity observation. Days-to-liquidate requires user order size and participation rate.

Beta/correlation require an aligned qualified benchmark and a defined minimum sample; VaR/ES require explicit horizon/confidence/window. Portfolio outputs require dated holdings/weights. Backtests require point-in-time signals, one-session execution lag unless proven executable, costs/slippage, bias disclosures, and historical constituents. Current runtime has unknown price adjustment/volume semantics, no holdings, benchmark alignment, or point-in-time signals, so all outputs fail closed.
