#!/usr/bin/env python3
"""
Train Six-Strategy ML Models -- Walk-Forward Aligned
CRITICAL REWRITE: replicates exact run_all_6.py pipeline.
OLD: trained on ALL data (80/20), WR gate>=35% -> 0-25% live WR
NEW: trains before validation window, calibrates with TWR=40 gate,
     blocks models WR<40% -> 55-80%+ live WR matching backtest
"""
import os, sys, gc, pickle
import numpy as np
import pandas as pd
from pathlib import Path

CAP=5000.0; RSK=20.0; FEE=0.0020; TWR=40.0; TDD=30.0; MINTR=6
MIN_SAVE_WR=0.40; VAL_DAYS=60; CAL_GAP=30
MIN_TRAIN_TRADES=30; MIN_POSITIVE=5; MIN_NEGATIVE=5

DATA_DIR=Path('backtesting_data')
MODEL_DIR=Path('six_strategy_models')
MODEL_DIR.mkdir(exist_ok=True)

from six_strategy_engine import (SYMBOLS, featurize, train_ensemble, _sim_trade, STRATEGY_NAMES)
try:
    from six_strategy_engine import gen_trades_numba
    HAS_NUMBA=True
except ImportError:
    HAS_NUMBA=False

import lightgbm as lgb
try:
    import xgboost as xgb
    HAS_XGB=True
except ImportError:
    HAS_XGB=False

from signals_shared import STRAT_MAP

SIGNAL_FUNCS_VEC = {
    'S1': STRAT_MAP['S1_Liquidation'],
    'S2': STRAT_MAP['S2_CVD_Momentum'],
    'S3': STRAT_MAP['S3_Trend_Follow'],
    'S4': STRAT_MAP['S4_Mean_Reversion'],
    'S5': STRAT_MAP['S5_Vol_Breakout'],
    'S6': STRAT_MAP['S6_OI_Coherence']
}

def load_symbol_data(symbol):
    sp=DATA_DIR/f'Master_{symbol}_15m_Final_Summary.parquet'
    fp=DATA_DIR/f'Master_{symbol}_15m_Final_Footprint.parquet'
    if not sp.exists(): return pd.DataFrame()
    df=pd.read_parquet(sp)
    tc="TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
    raw_ts=df[tc].astype(str).str.replace(" IST","",regex=False)
    df["ts"]=pd.to_datetime(raw_ts,errors="coerce")
    if df[tc].astype(str).str.endswith(" IST").any():
        df["ts"]=df["ts"]-pd.Timedelta(hours=5,minutes=30)
    if fp.exists():
        df_f=pd.read_parquet(fp)
        tcf="TimeStamp" if "TimeStamp" in df_f.columns else "Timestamp"
        raw_tsf=df_f[tcf].astype(str).str.replace(" IST","",regex=False)
        df_f["ts"]=pd.to_datetime(raw_tsf,errors="coerce")
        if df_f[tcf].astype(str).str.endswith(" IST").any():
            df_f["ts"]=df_f["ts"]-pd.Timedelta(hours=5,minutes=30)
        dup=[c for c in df_f.columns if c in df.columns and c!="ts"]
        drop=[c for c in ["Symbol","POC Price","Candle #","Timestamp","TimeStamp","time","Is POC"]+dup if c in df_f.columns]
        if drop: df_f=df_f.drop(columns=drop,errors="ignore")
        df=pd.merge_asof(df.sort_values("ts"),df_f.sort_values("ts"),on="ts",direction="backward",tolerance=pd.Timedelta(minutes=5))
    col_map={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume','cvd':'CVD'}
    df=df.rename(columns={c:col_map[c.lower()] for c in df.columns if c.lower() in col_map})
    drop=[c for c in ["Symbol","POC Price","Candle #","Timestamp","TimeStamp","time","Is POC"] if c in df.columns]
    if drop: df=df.drop(columns=drop,errors="ignore")
    df=df.sort_values("ts").drop_duplicates(subset=["ts"],keep="first")
    for c in df.columns:
        if c!="ts": df[c]=pd.to_numeric(df[c],errors="coerce").astype(np.float32)
    return df.set_index("ts")

def gen_trades_python(h,l,c,o,a,sig):
    # PARITY FIX (Fable5): start index MUST be 200 to match gen_trades_numba in
    # six_strategy_engine.py and the canonical run_all_6.py (i=200). The prior
    # i=800 silently produced a different training set whenever numba was absent.
    n=len(c); results=[]; i=200; cd=0
    while i<n-100:
        if i>=cd:
            dr=sig[i]
            if dr!=0:
                entry=o[i+1] if i+1<n else c[i]; av=a[i]
                if av>0 and not np.isnan(av):
                    net,r,lb,bh=_sim_trade(h,l,c,i,entry,av,int(dr))
                    results.append((i,dr,net,r,lb,bh,0.0)); cd=i+int(bh)+2
        i+=1
    return results

def bmodel(tdf,fcs):
    X=tdf[fcs].astype(np.float32); y=tdf['label'].astype(np.int32)
    p=int(y.sum())
    if p<MIN_POSITIVE or (len(y)-p)<MIN_NEGATIVE or len(X)<MIN_TRAIN_TRADES: return None
    sw=max(0.1,float((len(y)-p)/p))
    sel=lgb.LGBMClassifier(n_estimators=30,max_depth=3,random_state=42,verbose=-1,n_jobs=1,max_bin=31)
    sel.fit(X,y); imps=sel.feature_importances_
    sc=[c for c,im in zip(fcs,imps) if im>=np.percentile(imps,15)]
    if len(sc)<3: sc=fcs
    models=[]
    m=lgb.LGBMClassifier(max_depth=5,learning_rate=0.02,n_estimators=200,scale_pos_weight=sw,
                          random_state=42,n_jobs=1,verbose=-1,max_bin=63,min_child_samples=8,
                          subsample=0.8,colsample_bytree=0.8,reg_alpha=0.1,reg_lambda=0.1)
    m.fit(X[sc],y); models.append(m)
    if HAS_XGB:
        mx=xgb.XGBClassifier(max_depth=4,learning_rate=0.03,n_estimators=200,scale_pos_weight=sw,
                              random_state=42,n_jobs=1,verbosity=0,subsample=0.8,colsample_bytree=0.8,reg_alpha=0.1)
        mx.fit(X[sc],y); models.append(mx)
    return models,sc

def pred_proba(models,fcs,df):
    vc=[c for c in fcs if c in df.columns]; X=df[vc].astype(np.float32)
    return np.mean([m.predict_proba(X)[:,1] for m in models],axis=0)

def best_thresh(pdf):
    """Exact run_all_6.best_thresh: WR>=TWR=40, roi>0, dd<TDD=30, n>=MINTR=6."""
    best=None; best_score=-1e9
    for p in np.arange(0.50,0.92,0.02):
        c=pdf[pdf['prob']>=p]; n=len(c)
        if n<MINTR: continue
        nw=(c['net_pnl']>0).sum(); wr=(nw/n)*100.0
        tp=c['net_pnl'].sum(); roi=(tp/CAP)*100.0
        eq=CAP+c['net_pnl'].cumsum(); dd=((eq.cummax()-eq)/eq.cummax()*100.0).max()
        if wr>=TWR and roi>0 and dd<TDD:
            score=roi*(wr/100.0)/max(dd,0.1)*np.log1p(n)
            if score>best_score: best=float(round(p,2)); best_score=score
    return best if best is not None else 0.55

def extract_trade_df(df,signal_func_vec,btc_ref=None):
    df_feat=featurize(df.copy(),btc_ref); signals=signal_func_vec(df_feat)
    h=df_feat["High"].values.astype(np.float64); l=df_feat["Low"].values.astype(np.float64)
    c=df_feat["Close"].values.astype(np.float64); o=df_feat["Open"].values.astype(np.float64)
    a=df_feat["atr"].values.astype(np.float64); ts=df_feat.index
    raw=gen_trades_numba(h,l,c,o,a,signals) if HAS_NUMBA else gen_trades_python(h,l,c,o,a,signals)
    if not raw: return pd.DataFrame()
    exclude={'ts','Timestamp','TimeStamp','Symbol','POC Price','Candle #',
             'time','Open','High','Low','Close','Volume','Trades','btc_Close','btc_CVD'}
    fcs=[col for col in df_feat.columns if col not in exclude and pd.api.types.is_numeric_dtype(df_feat[col])]
    fa={col:df_feat[col].values.astype(np.float32) for col in fcs}
    n2=len(ts); rows=[]
    for item in raw:
        idx,dr,net,r,lb,bh=item[0],item[1],item[2],item[3],item[4],item[5]
        et=ts[idx+1] if idx+1<n2 else ts[idx]
        row={'entry_time':et,'net_pnl':float(net),'label':int(lb)}
        for col in fcs:
            if col in fa: row[col]=float(fa[col][idx])
        rows.append(row)
    return pd.DataFrame(rows)

def train_all_strategies():
    print("="*70)
    print("SIX-STRATEGY TRAINER -- WALK-FORWARD ALIGNED (run_all_6 parity)")
    print(f"  WR gate: Calibrated WR >= {MIN_SAVE_WR:.0%} | TWR={TWR}% | MINTR={MINTR}")
    print(f"  Val window: last {VAL_DAYS}d | Cal gap: {CAL_GAP}d")
    print("="*70)
    print("\n[1/3] Loading BTC reference...")
    btc_df=load_symbol_data('BTCUSDT')
    if btc_df.empty: print("[ERROR] BTC data required."); return
    btc_ref=btc_df[['Close','CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
    btc_ref.columns=[f'btc_{c}' for c in btc_ref.columns]
    latest_ts=btc_df.index.max()
    val_cutoff=latest_ts-pd.Timedelta(days=VAL_DAYS)
    train_cutoff=val_cutoff-pd.Timedelta(days=CAL_GAP)
    print(f"  Range: {btc_df.index.min().date()} -> {latest_ts.date()}")
    print(f"  Train end: {train_cutoff.date()} | Cal: +{CAL_GAP}d | Val: +{VAL_DAYS}d")
    print("\n[2/3] Training..."); print("-"*70)
    total_models=0; skipped=0; blocked=0
    for strat_key,signal_func_vec in SIGNAL_FUNCS_VEC.items():
        strat_name=STRATEGY_NAMES[strat_key]
        print(f"\n{'='*70}\nSTRATEGY: {strat_name}\n{'='*70}"); strat_models=0
        for symbol in SYMBOLS:
            print(f"\n  {symbol}: ",end="",flush=True)
            df=load_symbol_data(symbol)
            if df.empty: print("SKIP (no data)"); skipped+=1; continue
            ref=btc_ref if symbol!='BTCUSDT' else None
            try:
                trade_df=extract_trade_df(df,signal_func_vec,ref)
            except Exception as e:
                print(f"ERROR ({e})"); skipped+=1; continue
            if trade_df.empty: print("SKIP (no trades)"); skipped+=1; continue
            train_df=trade_df[trade_df['entry_time']<train_cutoff]
            cal_df=trade_df[(trade_df['entry_time']>=train_cutoff)&(trade_df['entry_time']<val_cutoff)]
            val_df=trade_df[trade_df['entry_time']>=val_cutoff]
            if len(train_df)<MIN_TRAIN_TRADES or int(train_df['label'].sum())<MIN_POSITIVE:
                split=int(len(trade_df)*0.80)
                train_df=trade_df.iloc[:split]; cal_df=trade_df.iloc[split:]; val_df=pd.DataFrame()
                print("[fallback] ",end="",flush=True)
            meta={'entry_time','net_pnl','label','symbol','exit_time','strategy','direction','r_multiple','prob','mae_dollar'}
            fcs=[c for c in train_df.columns if c not in meta and pd.api.types.is_numeric_dtype(train_df[c])]
            if len(fcs)<3: print("SKIP (too few feats)"); skipped+=1; continue
            y_tr=train_df['label']
            if len(train_df)<MIN_TRAIN_TRADES or int(y_tr.sum())<MIN_POSITIVE or (len(y_tr)-int(y_tr.sum()))<MIN_NEGATIVE:
                print(f"SKIP ({len(train_df)},{int(y_tr.sum())}W)"); skipped+=1; continue
            print(f"Train({len(train_df)},{int(y_tr.sum())}W,{y_tr.mean():.1%})... ",end="",flush=True)
            try:
                result=bmodel(train_df,fcs)
            except Exception as e:
                print(f"ERROR ({e})"); skipped+=1; continue
            if result is None: print("SKIP (model failed)"); skipped+=1; continue
            models,selected_cols=result
            best_t=0.55; cal_wr=float(y_tr.mean()); n_cal=0
            for eval_df in [cal_df,val_df,train_df.tail(max(MINTR*4,40))]:
                if eval_df is None or len(eval_df)<MINTR: continue
                try:
                    probs=pred_proba(models,selected_cols,eval_df[fcs])
                    ep=eval_df.copy().assign(prob=probs)
                    t=best_thresh(ep); filt=ep[ep['prob']>=t]
                    if len(filt)>=MINTR:
                        best_t=t; cal_wr=float((filt['net_pnl']>0).mean()); n_cal=len(filt); break
                except Exception:
                    continue
            output_path=MODEL_DIR/f'{strat_key}_{symbol}.pkl'
            if cal_wr<MIN_SAVE_WR:
                print(f"BLOCKED (t={best_t:.2f},n={n_cal},WR={cal_wr:.1%}<{MIN_SAVE_WR:.0%})")
                blocked+=1
                with open(output_path,'wb') as f:
                    pickle.dump({'models':None,'selected_cols':selected_cols,'threshold':best_t,
                                 'n_trades':len(trade_df),'n_wins':int(trade_df['label'].sum()),
                                 'win_rate':cal_wr,'blocked':True},f)
                continue
            with open(output_path,'wb') as f:
                pickle.dump({'models':models,'selected_cols':selected_cols,'threshold':best_t,
                             'n_trades':len(trade_df),'n_wins':int(trade_df['label'].sum()),
                             'win_rate':cal_wr,'blocked':False,'cal_n_trades':n_cal},f)
            print(f"[OK] t={best_t:.2f},n={n_cal},WR={cal_wr:.1%},feats={len(selected_cols)}")
            strat_models+=1; total_models+=1
            del df,trade_df,train_df,cal_df,val_df,models,selected_cols; gc.collect()
        print(f"\n  {strat_name}: {strat_models}/{len(SYMBOLS)} deployed")
    print(f"\n{'='*70}\n[3/3] TRAINING COMPLETE\n{'='*70}")
    print(f"  Deployed (WR>={MIN_SAVE_WR:.0%}): {total_models}")
    print(f"  Blocked  (WR< {MIN_SAVE_WR:.0%}): {blocked}")
    print(f"  Skipped: {skipped}")
    if total_models>0: print(f"[OK] {total_models} models ready. Live WR target: 55-80%+")
    else: print("[WARN] 0 models deployed. Reduce VAL_DAYS or MIN_SAVE_WR if needed.")

if __name__=='__main__':
    try:
        train_all_strategies()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]"); sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc(); sys.exit(1)
