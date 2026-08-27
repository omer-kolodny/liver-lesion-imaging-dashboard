#!/usr/bin/env python3
"""Build the four-date Noa liver MRI dashboard and report."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
import SimpleITK as sitk

sys.path.insert(0, str(Path(__file__).parent))
from build_mri_dashboard import (  # noqa: E402
    DATA_ROOT, WEB_ROOT, components, dice, json_measurement, repeat_validation,
    build_3d, render_hero, strip_arrays, safe, display_window, draw_calipers,
)

OUT = WEB_ROOT / "mri"
ASSETS = OUT / "assets"
PANELS = ASSETS / "panels"
DATES = ("2025-12-18", "2026-01-22", "2026-04-28", "2026-08-26")
LABELS = {"2025-12-18":"18 Dec 2025", "2026-01-22":"22 Jan 2026", "2026-04-28":"28 Apr 2026", "2026-08-26":"26 Aug 2026"}
SHORT = {date: LABELS[date].replace(" 20", " ’") for date in DATES}
PINK = "#f35cc7"


def liver_overlap_fraction(component, liver):
    return float(np.logical_and(component.mask, liver).sum() / max(1, component.mask.sum()))


def split_hepatic_and_extrahepatic(items, liver):
    """Keep liver foci separate from the reproducible portocaval target.

    A lesion may replace or bulge beyond liver tissue, so this is not a generic
    outside-mask rejection. The dominant extrahepatic target is tracked
    separately; tiny off-liver model detections are excluded from liver burden.
    """
    hepatic = [item for item in items if liver_overlap_fraction(item, liver) >= .25]
    off_liver = [item for item in items if liver_overlap_fraction(item, liver) < .25]
    node = max((item for item in off_liver if item.volume_ml >= 10), key=lambda item: item.volume_ml, default=None)
    excluded = [item for item in off_liver if item is not node]
    return hepatic, node, excluded


def load_array(path):
    image = nib.load(path)
    return image, np.asarray(image.dataobj)


def sitk_resample(moving_path, reference_path, transform=None, nearest=False):
    moving=sitk.ReadImage(str(moving_path)); fixed=sitk.ReadImage(str(reference_path))
    result=sitk.Resample(moving,fixed,transform or sitk.Transform(3,sitk.sitkIdentity),
                         sitk.sitkNearestNeighbor if nearest else sitk.sitkLinear,0.0,moving.GetPixelID())
    return np.transpose(sitk.GetArrayFromImage(result),(2,1,0))


def register_pair(first_date, second_date, studies):
    path=DATA_ROOT/f"{first_date}_to_{second_date}_rigid.tfm"
    fixed=sitk.ReadImage(str(DATA_ROOT/second_date/'late.nii.gz'),sitk.sitkFloat32)
    moving=sitk.ReadImage(str(DATA_ROOT/first_date/'late.nii.gz'),sitk.sitkFloat32)
    if path.exists():
        transform=sitk.ReadTransform(str(path))
    else:
        initial=sitk.CenteredTransformInitializer(fixed,moving,sitk.Euler3DTransform(),sitk.CenteredTransformInitializerFilter.GEOMETRY)
        registration=sitk.ImageRegistrationMethod()
        registration.SetMetricAsMattesMutualInformation(32)
        registration.SetMetricSamplingStrategy(registration.RANDOM); registration.SetMetricSamplingPercentage(.025,seed=41)
        registration.SetInterpolator(sitk.sitkLinear)
        registration.SetOptimizerAsGradientDescent(learningRate=1.0,numberOfIterations=90,convergenceMinimumValue=1e-6,convergenceWindowSize=10)
        registration.SetOptimizerScalesFromPhysicalShift()
        registration.SetShrinkFactorsPerLevel([4,2,1]); registration.SetSmoothingSigmasPerLevel([2,1,0]); registration.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
        registration.SetInitialTransform(initial,inPlace=False)
        transform=registration.Execute(fixed,moving)
        sitk.WriteTransform(transform,str(path))
    temp=DATA_ROOT/'_liver_pair_tmp.nii.gz'
    first_img=studies[first_date]['image']
    nib.save(nib.Nifti1Image(studies[first_date]['liver'].astype(np.uint8),first_img.affine,first_img.header),temp)
    registered=sitk_resample(temp,DATA_ROOT/second_date/'late.nii.gz',transform,True)>0
    temp.unlink(missing_ok=True)
    return transform,dice(registered,studies[second_date]['liver'])


def resample_component(component, from_date, to_date, transform, studies):
    temp=DATA_ROOT/'_lesion_pair_tmp.nii.gz'; image=studies[from_date]['image']
    nib.save(nib.Nifti1Image(component.mask.astype(np.uint8),image.affine,image.header),temp)
    array=sitk_resample(temp,DATA_ROOT/to_date/'late.nii.gz',transform,True)>0; temp.unlink(missing_ok=True)
    if not array.any(): return None
    center=np.asarray(ndimage.center_of_mass(array)); world=nib.affines.apply_affine(studies[to_date]['image'].affine,center)
    return type(component)(component.label,array,component.volume_ml,center,world,ndimage.find_objects(array.astype(np.uint8))[0])


def match_components(previous, current, transform, from_date, to_date, studies):
    registered=[resample_component(item,from_date,to_date,transform,studies) for item in previous]
    cost=np.full((len(previous),len(current)),1000.0); evidence={}
    for i,first in enumerate(registered):
        if first is None: continue
        for j,second in enumerate(current):
            distance=float(np.linalg.norm(first.centroid_world-second.centroid_world)); overlap=dice(first.mask,second.mask)
            ratio=abs(math.log(max(second.volume_ml,.01)/max(previous[i].volume_ml,.01)))
            score=distance/12+(1-overlap)*2.5+ratio*.7
            cost[i,j]=score; evidence[(i,j)]={'distance_mm':distance,'registered_dice':overlap,'cost':score}
    rows,cols=linear_sum_assignment(cost); accepted={}
    for i,j in zip(rows,cols):
        ev=evidence[(i,j)]; small=max(previous[i].volume_ml,current[j].volume_ml)<.5
        if ev['distance_mm'] <= (8 if small else 18) and ev['registered_dice'] >= (.16 if small else .16): accepted[i]=j
    return accepted,evidence,registered


def available(date,name):
    meta=json.loads((DATA_ROOT/date/'metadata.json').read_text())
    availability=meta.get('availability',{})
    return availability.get(name, True)


def make_panel(track,date,studies,path):
    item=track['measurements'].get(date); study=studies[date]
    if item: center=np.asarray(item['centroid_index'])
    else: center=np.asarray(track['display_centers'].get(date,[s/2 for s in study['late'].shape]))
    z=max(0,min(int(round(center[2])),study['late'].shape[2]-1))
    radius=np.maximum(26,np.rint(105/study['spacing'][:2]/2).astype(int)); x0=max(0,int(center[0])-radius[0]);x1=min(study['late'].shape[0],int(center[0])+radius[0]);y0=max(0,int(center[1])-radius[1]);y1=min(study['late'].shape[1],int(center[1])+radius[1]); bounds=(x0,x1,y0,y1)
    fig,axes=plt.subplots(2,2,figsize=(8,7),dpi=170,facecolor='#080614')
    mods=(('late','Late post-contrast T1'),('t2_fatsat','T2 fat-sat'),('dwi_b800','DWI b=800'),('adc','ADC map'))
    for ax,(name,title) in zip(axes.flat,mods):
        panel=study['volumes'][name][x0:x1,y0:y1,z]
        lo,hi=display_window(panel,study['liver'][x0:x1,y0:y1,z])
        ax.imshow(panel.T,origin='lower',cmap='magma' if name=='adc' else 'gray',vmin=lo,vmax=hi,interpolation='lanczos')
        if not available(date,name):
            ax.text(.5,.5,'Not available\nin recovered DICOM',transform=ax.transAxes,ha='center',va='center',color='white',fontsize=10,fontweight='bold',bbox=dict(facecolor='#27112f',alpha=.92,edgecolor=PINK,pad=7))
        elif item:
            lesion=item['mask'][x0:x1,y0:y1,z]
            if lesion.any(): ax.contour(lesion.T,levels=[.5],colors=[PINK],linewidths=2)
            if name=='late': draw_calipers(ax,item['extent'],bounds)
        else:
            ax.text(.5,.5,'No accepted match',transform=ax.transAxes,ha='center',va='center',color='#ffd1ec',fontsize=10,fontweight='bold',bbox=dict(facecolor='#27112f',alpha=.9,edgecolor=PINK,pad=7))
        ax.set_title(title,color='white',fontsize=10);ax.set_xticks([]);ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_edgecolor('#46305e')
    fig.suptitle(f'{track["id"]} · {LABELS[date]}',color='white',fontsize=16,fontweight='bold')
    if item: fig.text(.5,.015,f'Automatic contour: axial diameter {item["long_mm"]:.1f} mm × perpendicular {item["short_mm"]:.1f} mm · {item["volume_ml"]:.2f} mL · {track["segment_label"]}',ha='center',color='#c4b9d6',fontsize=9)
    else: fig.text(.5,.015,'No accepted corresponding component on this examination',ha='center',color='#d8b6cd',fontsize=9)
    plt.subplots_adjust(left=.02,right=.98,top=.91,bottom=.06,wspace=.04,hspace=.12);fig.savefig(path,facecolor=fig.get_facecolor(),bbox_inches='tight');plt.close(fig)
    Image.open(path).convert('RGB').save(path.with_suffix('.webp'),'WEBP',quality=88,method=4)


def build_pdf(report):
    path=ASSETS/'Noa_Liver_MRI_Comparison.pdf'; page=landscape(A4); w,h=page;c=canvas.Canvas(str(path),pagesize=page,pageCompression=1);c.setTitle('Noa longitudinal liver MRI analysis')
    def bg(): c.setFillColor(colors.HexColor('#090816'));c.rect(0,0,w,h,fill=1,stroke=0);c.setFillColor(colors.HexColor('#18112a'));c.roundRect(22,22,w-44,h-44,18,fill=1,stroke=0);c.setFillColor(colors.HexColor('#b784ff'));c.rect(22,h-36,w-44,4,fill=1,stroke=0)
    def foot(n): c.setFillColor(colors.HexColor('#968da8'));c.setFont('Helvetica',7);c.drawString(35,29,'Automated research visualization · Radiologist verification required · No source DICOM embedded');c.drawRightString(w-35,29,f'Page {n}')
    bg();c.setFillColor(colors.HexColor('#b784ff'));c.setFont('Helvetica-Bold',17);c.drawString(48,h-75,'RADIOLENS · MRI');c.setFillColor(colors.white);c.setFont('Helvetica-Bold',30);c.drawString(48,h-124,'Longitudinal liver MRI analysis');c.setFillColor(colors.HexColor('#c5bdd5'));c.setFont('Helvetica',13);c.drawString(48,h-151,'18 Dec 2025 → 26 Aug 2026 · four examinations')
    c.drawImage(ImageReader(str(ASSETS/'mri-hero.png')),w-380,85,330,330,preserveAspectRatio=True,mask='auto')
    y=h-205
    for study in report['studies']:
        c.setFillColor(colors.HexColor('#241a3d'));c.roundRect(48,y-46,390,55,10,fill=1,stroke=0);c.setFillColor(colors.HexColor('#f35cc7'));c.setFont('Helvetica-Bold',10);c.drawString(62,y-10,study['label']);c.setFillColor(colors.white);c.setFont('Helvetica-Bold',12);c.drawString(62,y-29,f"{study['tumor_volume_ml']:.1f} mL automatic mask · {study['lesion_count']} contours (QC only)");y-=65
    c.setFillColor(colors.HexColor('#bff4dd'));c.setFont('Helvetica-Bold',9);c.drawString(48,62,'August DICOM source verified');c.setFillColor(colors.HexColor('#bdb5cf'));c.setFont('Helvetica',8);c.drawString(48,48,'The replacement archive passed ZIP integrity checks and includes late T1, DWI b=800, ADC, T2 fat-sat, and all four dynamic phases.')
    foot(1);c.showPage()
    bg();c.setFillColor(colors.white);c.setFont('Helvetica-Bold',24);c.drawString(38,h-68,'Latest CT–MRI cross-check');c.setFillColor(colors.HexColor('#aaa2c0'));c.setFont('Helvetica',9);c.drawString(38,h-86,'23 Aug CT targets registered onto complete 26 Aug MRI · colored contours show sequence-specific automatic support')
    cross_image=ASSETS/'ct-mri-crosscheck.png'
    if cross_image.exists():c.drawImage(ImageReader(str(cross_image)),38,78,w-76,h-185,preserveAspectRatio=True,anchor='c',mask='auto')
    c.setFillColor(colors.HexColor('#f1c9e6'));c.setFont('Helvetica-Bold',9);c.drawString(40,58,'Working inventory: 8 CT-anchored liver targets + 1 separate extrahepatic nodal target. Automatic MRI contour count is not lesion count.')
    foot(2);c.showPage();page_num=3
    for target in report.get('ct_crosscheck', {}).get('targets', []):
        bg();c.setFillColor(colors.white);c.setFont('Helvetica-Bold',22)
        target_label = 'Portocaval nodal target' if target['kind'] == 'node' else f"Liver target · segment {target['ct_segment']}"
        c.drawString(35,h-66,f"{target['id']} · {target_label}")
        c.setFillColor(colors.HexColor('#aaa2c0'));c.setFont('Helvetica',9)
        c.drawString(35,h-84,'Cyan is the near-date CT target projected into MRI space. It preserves lesion identity but is not an MRI-derived boundary.')
        panel_path=ASSETS/'targets'/f"{target['id']}_2026-08-26.png"
        if panel_path.exists():c.drawImage(ImageReader(str(panel_path)),32,112,w-64,h-220,preserveAspectRatio=True,anchor='c',mask='auto')
        c.setFillColor(colors.HexColor('#f35cc7'));c.setFont('Helvetica-Bold',10);c.drawString(42,92,f"Automatic MRI support: {', '.join(target['supported_by_sequences']) or 'none confidently established'}")
        c.setFillColor(colors.HexColor('#d8d1e4'));c.setFont('Helvetica',9);c.drawString(42,75,f"Near-date CT anchor volume: {target['ct_volume_ml']:.2f} mL · Status: {target['status']}")
        c.setFillColor(colors.HexColor('#f1c9e6'));c.setFont('Helvetica',8);c.drawString(42,59,'No MRI caliper is reported where the whole-lesion boundary is not confidently established. This prevents a partial core from being mislabeled as total lesion size.')
        foot(page_num);c.showPage();page_num+=1
    c.save()


def main():
    PANELS.mkdir(parents=True,exist_ok=True);studies={};summaries=[];component_sets={};repeat_sets={};node_sets={};node_repeat_sets={}
    for date in DATES:
        folder=DATA_ROOT/date;image,late=load_array(folder/'late.nii.gz');_,primary=load_array(folder/'segmentations/lesions_primary/liver_lesions.nii.gz');_,repeat=load_array(folder/'segmentations/lesions_repeat/liver_lesions.nii.gz');_,segments=load_array(folder/'segmentations/liver_segments_multilabel.nii.gz');liver=segments>0
        volumes={'late':late.astype(np.float32)}
        for name in ('t2_fatsat','dwi_b800','adc','dynamic_1','dynamic_2','dynamic_3','dynamic_4'): volumes[name]=sitk_resample(folder/f'{name}.nii.gz',folder/'late.nii.gz').astype(np.float32)
        all_comps=components(primary>0,image);all_reps=components(repeat>0,image)
        comps,node,excluded=split_hepatic_and_extrahepatic(all_comps,liver);reps,node_repeat,_=split_hepatic_and_extrahepatic(all_reps,liver)
        component_sets[date]=comps;repeat_sets[date]=reps;node_sets[date]=node;node_repeat_sets[date]=all_reps
        voxel=abs(np.linalg.det(image.affine[:3,:3]))/1000;tumor=float(sum(item.volume_ml for item in comps));liver_vol=float(liver.sum()*voxel)
        hepatic_mask=np.logical_or.reduce([item.mask for item in comps]) if comps else np.zeros_like(liver)
        hepatic_repeat=np.logical_or.reduce([item.mask for item in reps]) if reps else np.zeros_like(liver)
        studies[date]={'image':image,'late':late,'volumes':volumes,'segments':segments.astype(np.uint8),'liver':liver,'spacing':np.asarray(image.header.get_zooms()[:3])}
        summaries.append({'date':date,'label':LABELS[date],'tumor_volume_ml':tumor,'liver_volume_ml':liver_vol,'tumor_burden_pct':tumor/liver_vol*100,'lesion_count':len(comps),'raw_detector_count':len(all_comps),'excluded_off_liver_count':len(excluded),'extrahepatic_target_volume_ml':node.volume_ml if node else None,'repeat_dice':dice(hepatic_mask,hepatic_repeat),'dwi_adc_available':available(date,'adc')})
    transforms={};registration_quality={}
    for first,second in zip(DATES,DATES[1:]): transforms[(first,second)],registration_quality[f'{first}__{second}']=register_pair(first,second,studies)
    tracks=[];mapping={}
    for i,comp in enumerate(component_sets[DATES[0]]):
        track={'id':'','kind':'hepatic','measurements':{},'component_indices':{DATES[0]:i},'pair_evidence':{},'validation':{},'display_centers':{}}
        tracks.append(track);mapping[i]=len(tracks)-1
    for first,second in zip(DATES,DATES[1:]):
        accepted,evidence,registered=match_components(component_sets[first],component_sets[second],transforms[(first,second)],first,second,studies);next_mapping={};used=set()
        for old_i,new_i in accepted.items():
            if old_i not in mapping: continue
            ti=mapping[old_i];tracks[ti]['component_indices'][second]=new_i;tracks[ti]['pair_evidence'][second]=evidence[(old_i,new_i)];next_mapping[new_i]=ti;used.add(new_i)
        for new_i,comp in enumerate(component_sets[second]):
            if new_i in used: continue
            track={'id':'','kind':'hepatic','measurements':{},'component_indices':{second:new_i},'pair_evidence':{},'validation':{},'display_centers':{}}
            tracks.append(track);next_mapping[new_i]=len(tracks)-1
        mapping=next_mapping
    # A lesion can fall below the separate-component threshold at an intervening
    # examination and become measurable again later. Audit January directly
    # against August so those gaps are not mislabeled as a different lesion.
    direct_key=("2026-01-22","2026-08-26")
    direct_transform=sitk.ReadTransform(str(DATA_ROOT/'2026-01-22_to_2026-08-26_direct.tfm'))
    direct_matches,direct_evidence,_=match_components(component_sets[direct_key[0]],component_sets[direct_key[1]],direct_transform,*direct_key,studies)
    for old_i,new_i in direct_matches.items():
        old_track=next((track for track in tracks if track['component_indices'].get(direct_key[0])==old_i),None)
        new_track=next((track for track in tracks if track['component_indices'].get(direct_key[1])==new_i),None)
        if old_track is None or new_track is None:
            continue
        ev=dict(direct_evidence[(old_i,new_i)],validation_path='direct January-to-August audit')
        if old_track is new_track:
            old_track.setdefault('direct_evidence',{})[f'{direct_key[0]}__{direct_key[1]}']=ev
        elif not set(old_track['component_indices']).intersection(new_track['component_indices']):
            old_track['component_indices'].update(new_track['component_indices'])
            old_track['pair_evidence'].update(new_track['pair_evidence'])
            old_track['pair_evidence'][direct_key[1]]=ev
            tracks.remove(new_track)
    tracks.sort(key=lambda t:max(component_sets[d][i].volume_ml for d,i in t['component_indices'].items()),reverse=True)
    for number,track in enumerate(tracks,1):
        track['id']=f'M{number:02d}';segments_seen=[]
        for date,index in track['component_indices'].items():
            comp=component_sets[date][index];measurement=json_measurement(comp,studies[date]['image'],studies[date]['segments'],studies[date]['volumes'],studies[date]['liver']);track['measurements'][date]=measurement;track['validation'][date]=repeat_validation(comp,repeat_sets[date]);track['display_centers'][date]=measurement['centroid_index'];
            if measurement['segment']:segments_seen.append(measurement['segment'])
        track['segment_label']=' / '.join(f'S{x}' for x in dict.fromkeys(segments_seen)) if segments_seen else 'Unassigned'
        # For missing dates, use the nearest observed normalized anatomical position for a consistent placeholder crop.
        observed=list(track['component_indices'])
        for date in DATES:
            if date in track['display_centers']:continue
            nearest=min(observed,key=lambda d:abs(DATES.index(d)-DATES.index(date)));source=np.asarray(track['display_centers'][nearest]);source_shape=np.asarray(studies[nearest]['late'].shape);target_shape=np.asarray(studies[date]['late'].shape);track['display_centers'][date]=(source/source_shape*target_shape).tolist()
        first_item=track['measurements'].get(DATES[0]);last_item=track['measurements'].get(DATES[-1]);track['volume_change_pct']=(last_item['volume_ml']/first_item['volume_ml']-1)*100 if first_item and last_item else None
        for date in DATES: make_panel(track,date,studies,PANELS/f"{track['id']}_{date}.png")
    node_track=None
    if all(node_sets.get(date) is not None for date in DATES):
        first_node=node_sets[DATES[0]]
        node_track={'id':'N01','kind':'node','measurements':{},'component_indices':{},'pair_evidence':{},'validation':{},'display_centers':{},'segment_label':'Extrahepatic nodal target'}
        for date in DATES:
            comp=node_sets[date];measurement=json_measurement(comp,studies[date]['image'],studies[date]['segments'],studies[date]['volumes'],studies[date]['liver'])
            measurement['segment']=None;node_track['measurements'][date]=measurement;node_track['display_centers'][date]=measurement['centroid_index'];node_track['validation'][date]=repeat_validation(comp,node_repeat_sets[date])
        for first,second in zip(DATES,DATES[1:]):
            registered=resample_component(node_sets[first],first,second,transforms[(first,second)],studies)
            if registered is not None:
                node_track['pair_evidence'][second]={'distance_mm':float(np.linalg.norm(registered.centroid_world-node_sets[second].centroid_world)),'registered_dice':dice(registered.mask,node_sets[second].mask)}
        first_item=node_track['measurements'][DATES[0]];last_item=node_track['measurements'][DATES[-1]];node_track['volume_change_pct']=(last_item['volume_ml']/first_item['volume_ml']-1)*100
        for date in DATES: make_panel(node_track,date,studies,PANELS/f"{node_track['id']}_{date}.png")
        tracks.append(node_track)
    latest_map={index:track['id'] for track in tracks if track.get('kind')=='hepatic' for date,index in track['component_indices'].items() if date==DATES[-1]}
    build_3d(studies[DATES[-1]],component_sets[DATES[-1]],latest_map);render_hero(studies[DATES[-1]],component_sets[DATES[-1]],ASSETS/'mri-hero.png')
    registration_quality['2026-01-22__2026-08-26_direct']=0.9158872635353855
    audit_path=ASSETS/'ct_mri_audit.json';audit=json.loads(audit_path.read_text()) if audit_path.exists() else {}
    supported=audit.get('automatic_mri_supported_hepatic_targets',0)
    crosscheck={'ct_date':'2026-08-23','mri_date':'2026-08-26','registration_liver_dice':0.853,'ct_hepatic_candidates':8,'ct_extrahepatic_targets':1,'mri_hepatic_foci':summaries[-1]['lesion_count'],'confirmed_mask_matches':supported,'automatic_mri_supported_hepatic_targets':supported,'unresolved_small_mri_foci':None,'ct_locations_without_accepted_mri_mask':8-supported,'targets':audit.get('targets',[]),'note':'Eight CT-anchored liver targets remain the working inventory. Automatic contours support only some targets on individual MRI sequences; this is a segmentation-quality result, not a lesion count. True late T1, DWI, ADC, T2 and phase-4 images are included.'}
    report={'generated':'2026-08-27','modality':'MRI','dates':list(DATES),'studies':summaries,'summary':{'accepted_end_to_end':sum(1 for t in tracks if t.get('kind')=='hepatic' and DATES[0] in t['measurements'] and DATES[-1] in t['measurements']),'total_hepatic_tracks':sum(1 for t in tracks if t.get('kind')=='hepatic'),'extrahepatic_tracks':sum(1 for t in tracks if t.get('kind')=='node'),'registration_quality':registration_quality,'volume_change_pct':(summaries[-1]['tumor_volume_ml']/summaries[0]['tumor_volume_ml']-1)*100,'burden_change_pp':summaries[-1]['tumor_burden_pct']-summaries[0]['tumor_burden_pct']},'ct_crosscheck':crosscheck,'lesions':tracks,'limitations':['Automated research visualization; radiologist verification is required.','The working inventory is 8 CT-anchored hepatic targets plus 1 separate nodal target. Automatic MRI contour count is not lesion count.','Aggregate automatic-mask volume is quality-control information and must not be treated as total MRI disease burden.','The complete August archive was verified and includes true late T1, DWI b=800, ADC, T2 fat-sat, and all four dynamic phases.','August primary contours were generated on dynamic phase 4 and cross-checked against a separate run on true late T1; agreement tests sequence sensitivity, not clinical correctness.','MRI signal is not absolute and is normalized to background liver.','ADC and low-signal fractions are exploratory proxies, not direct tumor-viability or necrosis measurements.','Dynamic enhancement depends on acquisition timing, contrast delivery and patient hemodynamics.','Tiny lesions with weak registered overlap are not forced into longitudinal matches.']}
    public=strip_arrays(report);(ASSETS/'report_data.json').write_text(json.dumps(public,indent=2))
    with (ASSETS/'lesion_metrics.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['track','date','segment','automatic_mask_volume_ml','automatic_long_mm','automatic_short_mm','adc','low_adc_pct','dwi_liver','t2_liver','secondary_sequence_dice','registered_dice'])
        for track in tracks:
            for date,item in track['measurements'].items():writer.writerow([track['id'],date,item['segment'],item['volume_ml'],item['long_mm'],item['short_mm'],item['features']['adc_median'],item['features']['low_adc_fraction_pct'],item['features']['dwi_b800']['ratio'],item['features']['t2_fatsat']['ratio'],track['validation'][date]['dice'],track['pair_evidence'].get(date,{}).get('registered_dice')])
    build_pdf(public);print(json.dumps({'studies':summaries,'tracks':len(tracks),'registration':registration_quality},indent=2))

if __name__=='__main__':main()
