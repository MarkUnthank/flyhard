#!/usr/bin/env python3
"""Plot actual recorded vehicle paths, never planned replacement motion."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flyhard.parking import body_center,rectangle


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    fig,axes=plt.subplots(len(a.runs),2,figsize=(12,5*len(a.runs)),squeeze=False)
    for row,root in enumerate(map(Path,a.runs)):
        spec=json.loads((root/'spec.json').read_text());report=json.loads((root/'metrics.json').read_text())
        for col,case in enumerate(spec['cases'][:2]):
            trace_path=root/str(case['seed'])/'frames.json' if spec['native'] else root/(str(case['seed'])+'.json')
            trace=json.loads(trace_path.read_text());states=np.array([r['state'] for r in trace]);xy=np.array([body_center(s) for s in states])
            ax=axes[row,col];ax.set_facecolor('#eeeeee');ax.axhspan(-case['width']/2,case['width']/2,color='#ddd')
            for yy in [-case['width']/2,case['width']/2]:ax.axhline(yy,c='#333',lw=2)
            for i in range(1,len(xy)):
                ax.plot(xy[i-1:i+1,0],xy[i-1:i+1,1],color='#32804a' if states[i,3]>=0 else '#d78420',lw=2)
            for index,color in [(0,'#666'),(-1,'#26723e')]:
                polygon=rectangle(*xy[index],states[index,2]);ax.fill(polygon[:,0],polygon[:,1],color=color,alpha=.2)
                ax.arrow(*xy[index],np.cos(states[index,2]),np.sin(states[index,2]),width=.05,color=color)
            goal=rectangle(case['goal_x'],case['goal_y'],np.pi)
            ax.plot(*np.vstack([goal,goal[0]]).T,'--',c='#333',label='target')
            result=next(r for r in report['trials_detail'] if r['seed']==case['seed'])
            name=('CARLA + measured body' if spec['native'] else 'Kinematic diagnostic')+(' | reset core' if spec['reset_core'] else ' | learned')
            ax.set_title(f"{name}\nseed {case['seed']} · {result['position_error_m']:.2f} m · {result['yaw_error_deg']:.1f}° · {'PASS' if result['success'] else 'not passed'}")
            ax.set_aspect('equal');ax.set_ylim(-6,6);ax.set_xlim(-10,7);ax.set_xlabel('metres' if row==len(a.runs)-1 else '');ax.set_ylabel('metres')
    fig.suptitle('Flyhard | three-point-turn pilot\nGreen = forward · amber = reverse · dashed box = target',fontsize=15)
    fig.tight_layout(rect=(0,0,1,.94),h_pad=3.); fig.savefig(a.out,dpi=150);plt.close(fig)

if __name__=='__main__':main()
