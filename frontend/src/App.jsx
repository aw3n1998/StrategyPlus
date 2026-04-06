import React, { useState, useEffect } from 'react';
import { 
  Cpu, LayoutDashboard, History, Settings, Bell, 
  Terminal as TerminalIcon, ExternalLink, RefreshCw, ChevronDown, Activity
} from 'lucide-react';

import { Overview } from './components/Overview';
import SymbolDetail from './components/SymbolDetail';
import TradeTable from './components/TradeTable';
import { SingularityChart } from './components/SingularityChart';
import StrategyEquityCurve from './components/StrategyEquityCurve';

const API_BASE = 'http://localhost:8000/api';

const App = () => {
  const [data, setData] = useState({
    overview: null,
    status: {},
    trades: [],
    equityCurve: {},
    equityCurveByStrategy: {},
    volatility: {},
    config: null,
    strategies: null,
    activeStrategies: [],
  });
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [strategyDropdownOpen, setStrategyDropdownOpen] = useState(false);

  const fetchData = async () => {
    try {
      const endpoints = ['overview', 'status', 'trades?limit=50', 'equity-curve', 'equity-curve-by-strategy', 'volatility', 'config', 'strategies'];
      const results = await Promise.all(
        endpoints.map(ep => fetch(`${API_BASE}/${ep.split('?')[0]}?${ep.split('?')[1] || ''}`).then(r => r.json()).catch(err => {
            console.warn(`Failed to fetch ${ep}`, err);
            return null;
        }))
      );
      
      const newData = {
        overview: results[0],
        status: results[1] || {},
        trades: results[2] || [],
        equityCurve: results[3] || {},
        equityCurveByStrategy: results[4] || {},
        volatility: results[5] || {},
        config: results[6],
        strategies: results[7]?.strategies || null,
        activeStrategies: results[7]?.active || [],
      };

      setData(newData);
      setLastUpdate(new Date());
      setLoading(false);

      if (!selectedSymbol && newData.overview?.symbols?.length > 0) {
        setSelectedSymbol(newData.overview.symbols[0]);
      }
    } catch (err) {
      console.error("Critical fetch error", err);
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, []);

  if (loading && !data.overview) {
    return (
      <div className="min-h-screen bg-quant-black-base text-quant-gold font-mono flex flex-col items-center justify-center">
        <Cpu className="size-16 animate-pulse mb-6 opacity-50" />
        <div className="w-48 h-1 bg-white/5 rounded-full overflow-hidden">
          <div className="h-full bg-quant-gold animate-[loading_2s_ease-in-out_infinite]"></div>
        </div>
        <p className="mt-4 text-[10px] uppercase tracking-[0.3em] text-gray-500">Initializing QuantOS Terminal...</p>
        <style dangerouslySetInnerHTML={{ __html: `@keyframes loading { 0% { width: 0%; transform: translateX(-100%); } 50% { width: 50%; } 100% { width: 0%; transform: translateX(200%); } }` }} />
      </div>
    );
  }

  const symbols = data.overview?.symbols || [];

  return (
    <div className="min-h-screen bg-quant-black-base text-quant-gold font-mono selection:bg-quant-gold selection:text-black flex flex-col">
      {/* Top Header */}
      <header className="border-b border-quant-black-border bg-black/80 backdrop-blur-xl sticky top-0 z-50 px-6 py-3 flex justify-between items-center shadow-2xl">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-quant-gold rounded-lg flex items-center justify-center shadow-[0_0_20px_rgba(212,175,55,0.3)]">
            <Cpu className="text-black size-6" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tighter italic uppercase flex items-center">
              Quant<span className="text-white">OS</span> 
              <span className="ml-2 px-1.5 py-0.5 bg-white/5 text-[8px] rounded border border-white/10 font-bold not-italic text-gray-400">V2.4</span>
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
               <span className={`w-1.5 h-1.5 rounded-full ${data.overview?.running ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
               <span className="text-[9px] font-bold uppercase tracking-widest text-gray-500">
                System {data.overview?.running ? 'Online' : 'Offline'}
               </span>
            </div>
          </div>

          {/* Strategy Selector */}
          <div className="relative">
            <button 
              onClick={() => setStrategyDropdownOpen(!strategyDropdownOpen)}
              className="flex items-center gap-2 px-4 py-2 bg-white/5 rounded-lg border border-white/10 hover:border-quant-gold/30 transition-all"
            >
              <Activity size={14} className="text-quant-gold" />
              <span className="text-xs font-bold text-white">
                {data.activeStrategies?.length > 0 
                  ? data.activeStrategies.map(id => data.strategies?.[id]?.name).filter(Boolean).join(', ')
                  : 'No Active Strategy'}
              </span>
              <ChevronDown size={12} className={`text-gray-500 transition-transform ${strategyDropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            
            {strategyDropdownOpen && data.strategies && (
              <div className="absolute top-full mt-2 right-0 w-64 bg-quant-black-card border border-quant-black-border rounded-xl overflow-hidden shadow-xl z-50">
                {Object.values(data.strategies).map(strategy => (
                  <button
                    key={strategy.id}
                    onClick={async () => {
                      await fetch(`${API_BASE}/strategy/switch`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({strategy_id: strategy.id})
                      });
                      setStrategyDropdownOpen(false);
                      fetchData();
                    }}
                    className={`w-full px-4 py-3 text-left flex items-center gap-3 border-b border-white/5 hover:bg-white/5 transition-all ${
                      data.activeStrategies.includes(strategy.id) ? 'bg-quant-gold/10 border-l-2 border-l-quant-gold' : ''
                    }`}
                  >
                    <div className="flex-1">
                      <p className="text-xs font-bold text-white">{strategy.name}</p>
                      <p className="text-[10px] text-gray-500">{strategy.description}</p>
                    </div>
                    {data.activeStrategies.includes(strategy.id) && (
                      <span className="text-[8px] font-bold text-quant-gold">ACTIVE</span>
                    )}
                  </button>
                ))}
                <button
                  onClick={() => {
                    setActiveTab('strategies');
                    setStrategyDropdownOpen(false);
                  }}
                  className="w-full px-4 py-3 text-left flex items-center gap-3 text-gray-500 hover:text-white transition-all"
                >
                  <span className="text-xs font-bold">Compare Strategies</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <nav className="hidden md:flex bg-white/5 rounded-xl p-1 border border-white/5">
           {[
             { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
             { id: 'trades', label: 'History', icon: History },
             { id: 'strategies', label: 'Strategies', icon: Activity },
             { id: 'config', label: 'Config', icon: Settings },
           ].map(tab => (
             <button
               key={tab.id}
               onClick={() => setActiveTab(tab.id)}
               className={`px-6 py-2 rounded-lg text-[10px] uppercase font-black tracking-widest flex items-center gap-2 transition-all ${
                 activeTab === tab.id 
                   ? 'bg-quant-gold text-black shadow-lg' 
                   : 'text-gray-500 hover:text-white'
               }`}
             >
               <tab.icon size={14} /> {tab.label}
             </button>
           ))}
        </nav>

        <div className="flex items-center gap-6">
           <div className="text-right hidden sm:block">
              <p className="text-[8px] text-gray-500 uppercase font-bold tracking-widest mb-0.5">Last Sync</p>
              <p className="text-[10px] text-white font-mono tabular-nums font-bold">
                {lastUpdate.toLocaleTimeString()}
              </p>
           </div>
           <button onClick={() => fetchData()} className="p-2 bg-white/5 rounded-full hover:bg-quant-gold/20 transition-all border border-white/5 group">
              <RefreshCw size={16} className="text-gray-500 group-hover:text-quant-gold" />
           </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 md:p-10 max-w-[1800px] mx-auto w-full">
        {activeTab === 'dashboard' && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
            <Overview overview={data.overview} symbols={symbols} />
            
            {/* Strategy Equity Curves */}
            <div className="mt-6">
              <StrategyEquityCurve 
                equityCurveByStrategy={data.equityCurveByStrategy}
                strategies={data.strategies}
              />
            </div>
            
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
              {/* Singularity Chart */}
              <div className="xl:col-span-4">
                <SingularityChart 
                  status={data.status} 
                  selectedSymbol={selectedSymbol}
                  symbols={symbols}
                />
              </div>
              
              {/* Left Column: Symbol Grid */}
              <div className="xl:col-span-8 space-y-8">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-black uppercase tracking-[0.3em] flex items-center gap-3">
                    <TerminalIcon size={18} className="text-quant-gold" />
                    Market Surveillance
                  </h2>
                  <div className="flex gap-2">
                    <span className="px-2 py-1 bg-white/5 border border-white/10 rounded text-[9px] text-gray-500 font-bold uppercase">Live</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {symbols.map(sym => (
                    <SymbolDetail 
                      key={sym}
                      symbol={sym}
                      status={data.status}
                      equityCurve={data.equityCurve}
                      volatility={data.volatility}
                      isSelected={selectedSymbol === sym}
                      onSelect={setSelectedSymbol}
                    />
                  ))}
                </div>
              </div>

              {/* Right Column: Alerts & Recent Activity */}
              <div className="xl:col-span-4 space-y-6">
                <div className="bg-quant-black-card border border-quant-black-border rounded-xl p-6 shadow-xl">
                  <h3 className="text-xs font-black uppercase tracking-widest mb-6 flex items-center gap-2 border-b border-white/5 pb-4">
                    <Bell size={14} className="text-quant-gold" /> Recent Notifications
                  </h3>
                  <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar text-[11px]">
                    {data.trades.slice(0, 5).map((t, i) => (
                      <div key={i} className="flex gap-4 p-3 rounded-lg bg-white/5 border border-white/5 hover:border-quant-gold/20 transition-all group">
                        <div className={`w-1 mt-1 rounded-full ${t.pnl_after_fees >= 0 ? 'bg-green-500' : 'bg-red-500'}`}></div>
                        <div className="flex-1">
                          <p className="font-bold text-white group-hover:text-quant-gold transition-colors">{t.symbol} Trade Closed</p>
                          <p className="text-gray-500 mt-0.5 uppercase tracking-tighter">
                            {t.direction} • PnL: <span className={t.pnl_after_fees >= 0 ? 'text-green-500' : 'text-red-500'}>
                              {t.pnl_after_fees >= 0 ? '+' : ''}{t.pnl_after_fees?.toFixed(2)} USDT
                            </span>
                          </p>
                        </div>
                        <ExternalLink size={12} className="text-gray-700 mt-1" />
                      </div>
                    ))}
                    {data.trades.length === 0 && (
                      <p className="text-center text-gray-700 py-10 uppercase tracking-widest text-[9px]">No recent alerts</p>
                    )}
                  </div>
                </div>

                <div className="bg-quant-gold/5 border border-quant-gold/20 rounded-xl p-6">
                  <h3 className="text-[10px] font-black uppercase tracking-widest mb-4 text-quant-gold">Terminal Info</h3>
                  <div className="space-y-3 text-[10px]">
                     <div className="flex justify-between border-b border-white/5 pb-2">
                        <span className="text-gray-500 uppercase">Engine</span>
                        <span className="text-white font-bold">Bitget CCXT.Pro</span>
                     </div>
                     <div className="flex justify-between border-b border-white/5 pb-2">
                        <span className="text-gray-500 uppercase">Uptime</span>
                        <span className="text-white font-bold">04:22:15</span>
                     </div>
                     <div className="flex justify-between">
                        <span className="text-gray-500 uppercase">API Latency</span>
                        <span className="text-green-500 font-bold">24ms</span>
                     </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'trades' && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <TradeTable trades={data.trades} />
          </div>
        )}

        {activeTab === 'config' && data.config && (
          <div className="bg-quant-black-card border border-quant-black-border rounded-xl p-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-sm font-black uppercase tracking-[0.3em] mb-8 flex items-center gap-3">
              <Settings size={20} className="text-quant-gold" />
              Engine Configuration
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(data.config).map(([key, value]) => (
                <div key={key} className="p-4 rounded-xl border border-white/5 bg-black/40 hover:border-quant-gold/30 transition-all">
                  <p className="text-[9px] text-gray-600 uppercase tracking-widest mb-2 font-bold">{key.replace(/_/g, ' ')}</p>
                  <p className="text-white font-black italic tracking-tighter truncate">
                    {typeof value === 'boolean' ? (value ? 'ENABLED' : 'DISABLED') : String(value)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="bg-quant-black-card border border-quant-black-border rounded-xl p-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-sm font-black uppercase tracking-[0.3em] mb-8 flex items-center gap-3">
              <Activity size={20} className="text-quant-gold" />
              Strategy Comparison
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {data.strategies && Object.values(data.strategies).map(strategy => (
                <div 
                  key={strategy.id}
                  className={`p-6 rounded-xl border transition-all ${
                    data.activeStrategies.includes(strategy.id) 
                      ? 'border-quant-gold bg-quant-gold/5 shadow-[0_0_30px_rgba(212,175,55,0.1)]' 
                      : 'border-white/10 bg-black/40 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-black text-white">{strategy.name}</h3>
                    {data.activeStrategies.includes(strategy.id) && (
                      <span className="px-2 py-1 bg-quant-gold text-black text-[8px] font-bold rounded">ACTIVE</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mb-4">{strategy.description}</p>
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Version</span>
                      <span className="text-white font-bold">{strategy.version}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Author</span>
                      <span className="text-white font-bold">{strategy.author}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Today's Trades</span>
                      <span className="text-white font-bold">{strategy.id === 'po3' ? data.overview?.total_trades || 0 : '-'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Today's PnL</span>
                      <span className={`font-bold ${strategy.id === 'po3' ? (data.overview?.total_pnl >= 0 ? 'text-green-500' : 'text-red-500') : 'text-gray-500'}`}>
                        {strategy.id === 'po3' ? `${data.overview?.total_pnl || 0} USDT` : '-'}
                      </span>
                    </div>
                  </div>
                  
                  <button
                    onClick={async () => {
                      if (strategy.id !== 'Coming Soon') {
                        await fetch(`${API_BASE}/strategy/switch`, {
                          method: 'POST',
                          headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({strategy_id: strategy.id})
                        });
                        fetchData();
                      }
                    }}
                    disabled={data.activeStrategies.includes(strategy.id) || strategy.author === 'Coming Soon'}
                    className={`w-full mt-6 py-3 rounded-lg text-xs font-black uppercase tracking-widest transition-all ${
                      data.activeStrategies.includes(strategy.id)
                        ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                        : strategy.author === 'Coming Soon'
                        ? 'bg-gray-800 text-gray-600 cursor-not-allowed'
                        : 'bg-quant-gold text-black hover:bg-white'
                    }`}
                  >
                    {data.activeStrategies.includes(strategy.id) ? 'Active' : 'Activate'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-quant-black-border p-4 bg-black text-[9px] text-center text-gray-700 uppercase tracking-[0.5em] font-bold">
        &copy; 2026 QuantOS Terminal // Secure Execution Environment
      </footer>
    </div>
  );
};

export default App;
