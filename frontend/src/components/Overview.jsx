import React from 'react';
import { Wallet, Trophy, Target, Activity, Coins } from 'lucide-react';

export const StatCard = ({ icon: Icon, label, value, sub, isGold }) => (
  <div className={`p-5 rounded-xl border transition-all duration-300 ${
    isGold 
      ? 'bg-quant-gold border-quant-gold text-black shadow-[0_0_40px_rgba(212,175,55,0.15)]' 
      : 'bg-quant-black-card border-quant-black-border text-quant-gold hover:border-quant-gold/40'
  }`}>
    <div className="flex justify-between items-start mb-3">
      <div className={`${isGold ? 'text-black/60' : 'text-gray-500'}`}>
        <Icon size={20} />
      </div>
      <div className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isGold ? 'bg-black/10' : 'bg-white/5'}`}>
        LIVE
      </div>
    </div>
    <p className={`text-[10px] uppercase tracking-[0.2em] mb-1 font-semibold ${isGold ? 'text-black/60' : 'text-gray-500'}`}>
      {label}
    </p>
    <h3 className="text-2xl font-black italic tracking-tight">
      {value}
    </h3>
    <p className={`text-[10px] mt-2 opacity-60 ${isGold ? 'text-black/70' : 'text-gray-400'}`}>
      {sub}
    </p>
  </div>
);

export const Overview = ({ overview, symbols }) => {
  if (!overview) return null;

  const capitalStr = overview.strategy_capitals 
    ? Object.entries(overview.strategy_capitals).map(([k, v]) => `${k}: ${v}U`).join(', ')
    : 'N/A';

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
      <StatCard 
        icon={Coins} 
        label="Simulated Capital" 
        value={`$${overview.total_capital || 0}`} 
        sub={capitalStr || 'Default 1000U each'} 
      />
      <StatCard 
        icon={Wallet} 
        label="Net Realized PnL" 
        value={`$${overview.total_pnl.toFixed(2)}`} 
        sub={`${overview.total_trades} total trades`} 
        isGold={overview.total_pnl >= 0} 
      />
      <StatCard 
        icon={Trophy} 
        label="Winning Rate" 
        value={`${overview.win_rate}%`} 
        sub={`${overview.total_trades} trades closed`} 
      />
      <StatCard 
        icon={Target} 
        label="Active Positions" 
        value={overview.active_positions} 
        sub={`Monitoring ${symbols.length} pairs`} 
      />
      <StatCard 
        icon={Activity} 
        label="System Status" 
        value={overview.running ? 'ONLINE' : 'OFFLINE'} 
        sub={overview.dry_run ? 'Dry Run Mode Enabled' : 'Live Trading Active'} 
      />
    </div>
  );
};
