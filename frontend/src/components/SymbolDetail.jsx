import React from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { TrendingUp, AlertTriangle, Zap } from 'lucide-react';

const SymbolDetail = ({ symbol, status, equityCurve, volatility, isSelected, onSelect }) => {
  const s = status[symbol];
  const vol = volatility[symbol];
  const curve = equityCurve[symbol] || [];

  if (!s) return null;

  return (
    <div 
      className={`bg-quant-black-card border rounded-xl overflow-hidden transition-all duration-500 ${
        isSelected ? 'border-quant-gold shadow-gold-glow scale-[1.01]' : 'border-quant-black-border hover:border-quant-gold/30'
      }`}
      onClick={() => onSelect(symbol)}
    >
      <div className="p-5 border-b border-quant-black-border bg-black/40 flex justify-between items-center">
        <div>
          <h3 className="text-sm font-black tracking-widest text-white group-hover:text-quant-gold transition-colors italic">
            {symbol}
          </h3>
          <p className="text-[10px] text-gray-500 mt-0.5">BITGET SWAP • 15M / 1M</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-black italic tracking-tighter text-white">${s.price?.toLocaleString() || '---'}</p>
          <div className="flex items-center gap-2 justify-end">
            <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${s.ws_health?.stale ? 'bg-red-500' : 'bg-green-500'}`}></span>
            <span className="text-[8px] text-gray-600 uppercase font-bold tracking-widest">LIVE FEED</span>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* Position or Detection State */}
        {s.position ? (
          <div className="bg-quant-gold/5 border border-quant-gold/20 p-4 rounded-lg relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-1">
               <Zap size={12} className="text-quant-gold animate-bounce" />
            </div>
            <div className="flex justify-between items-end mb-4">
              <div>
                <span className={`text-[10px] font-black px-2 py-0.5 rounded border ${
                  s.position.direction === 'long' 
                    ? 'bg-green-500/10 border-green-500/30 text-green-500' 
                    : 'bg-red-500/10 border-red-500/30 text-red-500'
                }`}>
                  {s.position.direction.toUpperCase()} POSITION
                </span>
                <p className="text-2xl font-black italic mt-1 text-white">
                  {s.position.contracts.toFixed(3)} <span className="text-[10px] align-middle text-gray-500 not-italic">CONT</span>
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] text-gray-500 uppercase font-bold mb-1">Unrealized PnL</p>
                <p className={`text-xl font-black italic ${(s.price - s.position.entry_price) * (s.position.direction === 'long' ? 1 : -1) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {((s.price - s.position.entry_price) * (s.position.direction === 'long' ? 1 : -1) * s.position.contracts).toFixed(2)} USDT
                </p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 border-t border-quant-gold/10 pt-3">
              <div>
                <p className="text-[9px] text-gray-500 uppercase">Entry</p>
                <p className="text-[11px] font-bold text-white">{s.position.entry_price.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-[9px] text-gray-500 uppercase">Stop Loss</p>
                <p className="text-[11px] font-bold text-red-400">{s.position.stop_loss.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-[9px] text-gray-500 uppercase">TP1 (Target)</p>
                <p className="text-[11px] font-bold text-green-400">{s.position.tp1.toFixed(2)}</p>
              </div>
            </div>
          </div>
        ) : s.manipulation ? (
          <div className="bg-yellow-500/5 border border-yellow-500/20 p-4 rounded-lg text-center">
            <p className="text-[10px] font-bold text-yellow-500 uppercase tracking-widest animate-pulse">Waiting for Entry Signal</p>
            <div className="mt-2 flex justify-center gap-4">
              <div>
                <p className="text-[8px] text-gray-600 uppercase">Bias</p>
                <p className="text-xs font-bold text-white">{s.manipulation.bias.toUpperCase()}</p>
              </div>
              <div>
                <p className="text-[8px] text-gray-600 uppercase">Level</p>
                <p className="text-xs font-bold text-white">{s.manipulation.extreme.toFixed(2)}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white/5 border border-white/5 p-4 rounded-lg text-center border-dashed">
            <p className="text-[10px] font-bold text-gray-600 uppercase tracking-[0.2em]">Scanning for Accumulation</p>
          </div>
        )}

        {/* Mini Chart */}
        {isSelected && curve.length > 0 && (
          <div className="h-24 mt-4">
             <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={curve}>
                  <Area type="monotone" dataKey="equity" stroke="#d4af37" fill="#d4af37" fillOpacity={0.1} strokeWidth={1} isAnimationActive={false} />
                </AreaChart>
             </ResponsiveContainer>
          </div>
        )}

        {/* Volatility Indicator */}
        {vol && (
          <div className={`mt-4 px-3 py-2 rounded-lg border flex justify-between items-center ${vol.is_safe ? 'bg-green-500/5 border-green-500/10' : 'bg-red-500/5 border-red-500/10'}`}>
            <div className="flex items-center gap-2">
              <AlertTriangle size={12} className={vol.is_safe ? 'text-green-500' : 'text-red-500'} />
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Volatility Risk</span>
            </div>
            <span className={`text-[10px] font-black ${vol.is_safe ? 'text-green-500' : 'text-red-500'}`}>
              {vol.is_safe ? 'LOW' : 'HIGH'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default SymbolDetail;
