import React from 'react';
import { Activity } from 'lucide-react';

const TradeTable = ({ trades }) => {
  return (
    <div className="bg-quant-black-card border border-quant-black-border rounded-xl overflow-hidden shadow-gold-glow">
      <div className="px-6 py-4 border-b border-quant-black-border flex justify-between items-center bg-black/20">
        <h2 className="text-sm font-bold uppercase tracking-widest flex items-center gap-2">
          <Activity size={16} className="text-quant-gold" /> 
          Trade History
        </h2>
        <span className="text-[10px] text-gray-500 uppercase">Latest {trades.length} Records</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[10px] text-gray-500 uppercase tracking-wider border-b border-quant-black-border bg-black/40 font-bold">
              <th className="py-4 px-6">Pair</th>
              <th className="py-4 px-6">Side</th>
              <th className="py-4 px-6 text-right">Entry</th>
              <th className="py-4 px-6 text-right">Exit</th>
              <th className="py-4 px-6 text-right">PnL</th>
              <th className="py-4 px-6 text-right">Fees</th>
              <th className="py-4 px-6">Status</th>
              <th className="py-4 px-6 text-right">Time</th>
            </tr>
          </thead>
          <tbody className="text-xs divide-y divide-white/5">
            {trades.length > 0 ? trades.map((t, i) => (
              <tr key={i} className="hover:bg-quant-gold/5 transition-colors group">
                <td className="py-4 px-6 font-bold text-white group-hover:text-quant-gold">{t.symbol}</td>
                <td className="py-4 px-6">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    t.direction === 'long' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'
                  }`}>
                    {t.direction.toUpperCase()}
                  </span>
                </td>
                <td className="py-4 px-6 text-right text-gray-400 tabular-nums">{t.entry_price?.toFixed(2)}</td>
                <td className="py-4 px-6 text-right text-gray-400 tabular-nums">{t.exit_price?.toFixed(2)}</td>
                <td className={`py-4 px-6 text-right font-black tabular-nums ${
                  t.pnl_after_fees >= 0 ? 'text-green-500' : 'text-red-500'
                }`}>
                  {t.pnl_after_fees >= 0 ? '+' : ''}{t.pnl_after_fees?.toFixed(2)}
                </td>
                <td className="py-4 px-6 text-right text-gray-600 tabular-nums">{t.fees_paid?.toFixed(4)}</td>
                <td className="py-4 px-6">
                  <span className={`text-[10px] font-bold ${
                    t.status === 'closed' ? 'text-gray-500' : 'text-quant-gold animate-pulse'
                  }`}>
                    {t.status.toUpperCase()}
                  </span>
                </td>
                <td className="py-4 px-6 text-right text-gray-600 tabular-nums">
                  {(t.holding_secs / 60)?.toFixed(0)}m
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan="8" className="py-20 text-center text-gray-700 italic">No trades recorded in current session</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TradeTable;
