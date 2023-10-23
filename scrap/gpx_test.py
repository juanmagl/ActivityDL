from datetime import datetime
import sys
import xml.etree.ElementTree as ET
import dateutil
import gpxpy
import numpy as np
import pandas as pd
import dateutil.parser as dp

def main():
    ns = {'': "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    ET.register_namespace('', ns[''])
    tcx = ET.ElementTree(file='in.tcx')
    #ET.indent(tree)
    #ET.dump(tree)
    
    # Obtain timepoints from tcx
    tcx_tkp_parent = { tkp: lp
              for acts in tcx.findall('Activities', namespaces=ns)
              for act in acts.findall('Activity', namespaces=ns)
              for lp in act.findall('Lap', namespaces=ns)
              for tk in lp.findall('Track', namespaces=ns)
              for tkp in tk.findall('Trackpoint', namespaces=ns)
    }
    tcx_tkp = list(tcx_tkp_parent.keys())
    tcx_tm = [dp.parse(tkp.find('Time', namespaces=ns).text) for tkp in tcx_tkp ]
    tcx_df = pd.DataFrame(index=tcx_tm)
    tcx_df[['latitude', 'longitude', 'elevation']] = np.nan
    tcx_elt_dict = dict(zip(tcx_tm, tcx_tkp))
    #tcx_df['tm'] = tcx_tm
    tcx_df.sort_index(inplace=True)
    tcx_startdate = np.min(tcx_df.index)
    tcx_enddate = np.max(tcx_df.index)

    print(f"TCX start: {tcx_startdate}, end: {tcx_enddate}")

    # Obtain gpx file
    try:
        gpx_file = open('loc.gpx', 'r')
    except:
        print('I cannot open gpx file')
        sys.exit(1)

    GPX_COLUMNS = ['time', 'latitude', 'longitude', 'elevation']
    gpx = gpxpy.parse(gpx_file)
    
    # Create dataframe with gpx points
    gpx_df = pd.DataFrame([[pt.time, pt.latitude, pt.longitude, pt.elevation]
                          for trk in gpx.tracks
                          for sgm in trk.segments
                          for pt in sgm.points
                          ], columns=GPX_COLUMNS)
    gpx_df = gpx_df.set_index('time')
    gpx_df.sort_index(inplace=True)
    
    # Trim gpx dataframe to include only timepoints in tcx plus one extra at start and end 
    tmp_series = gpx_df.index[gpx_df.index < tcx_startdate]
    gpx_from = tmp_series[-1] if len(tmp_series) > 0 else tcx_startdate
    tmp_series = gpx_df.index[gpx_df.index > tcx_enddate]
    gpx_to = tmp_series[0] if len(tmp_series) > 0 else tcx_enddate

    gpx_df = gpx_df[ (gpx_df.index >= gpx_from) & (gpx_df.index <= gpx_to) ]
    
    print(f"GPX from {gpx_from} to {gpx_to}")
    
    # Merge tcx dataframe and gpx dataframe and interpolate
    # If tcx contained positional data, it will be ignored
    tcx_df = pd.concat([gpx_df, tcx_df])
    tcx_df.index = pd.to_datetime(tcx_df.index, utc=True)
    tcx_df = tcx_df[~tcx_df.index.duplicated(keep='first')]
    tcx_df.sort_index(ascending=True, inplace=True)
    tcx_df['latitude'].interpolate(method='time', inplace=True)
    tcx_df['longitude'].interpolate(method='time', inplace=True)
    tcx_df['elevation'].interpolate(method='time', inplace=True)
    tcx_df = tcx_df[(tcx_df.index >= tcx_startdate) & (tcx_df.index <= tcx_enddate)]

    # Calculate distances and cumul distances
    tcx_df[['lat_prev', 'lon_prev', 'ele_prev']] = tcx_df[['latitude', 'longitude', 'elevation']].shift(1)
    tcx_df.loc[tcx_df.index[0], 'lat_prev'] = tcx_df.loc[tcx_df.index[0], 'latitude']
    tcx_df.loc[tcx_df.index[0], 'lon_prev'] = tcx_df.loc[tcx_df.index[0], 'longitude']
    tcx_df.loc[tcx_df.index[0], 'ele_prev'] = tcx_df.loc[tcx_df.index[0], 'elevation']
    tcx_df['dist'] = tcx_df.apply(lambda r: gpxpy.geo.distance(r['lat_prev'], r['lon_prev'], r['ele_prev'] if pd.notna(r['ele_prev']) else None,
                                  r['latitude'], r['longitude'], r['elevation'] if pd.notna(r['elevation']) else None),
                                  axis=1)
    tcx_df['cumul_dist'] = tcx_df['dist'].cumsum()
    total_dist = tcx_df['cumul_dist'].iloc[-1]
    print(f"Total distance (GPX): {total_dist}")
    
    #tcx_df.to_csv('test.csv')
    
    # Update tcx tree
    def create_position_elevation(p, elt_dict):
        tm = p.name
        lat = str(p['latitude']) if p['latitude'] is not np.nan else None
        lon = str(p['longitude']) if p['longitude'] is not np.nan else None
        ele = str(p['elevation']) if p['elevation'] is not np.nan else None
        tkp_elt = elt_dict.get(tm)
        if (lat is not None) & (lon is not None) & (tkp_elt is not None):
            pos_elt = ET.Element('Position')
            tkp_elt.insert(1, pos_elt)
            lat_elt = ET.SubElement(pos_elt, 'LatitudeDegrees')
            lat_elt.text = lat
            lon_elt = ET.SubElement(pos_elt, 'LongitudeDegrees')
            lon_elt.text = lon
            if ele is not None:
                alt_elt = ET.Element('AltitudeMeters')
                tkp_elt.insert(2, alt_elt)
                alt_elt.text = ele

    tcx_df.apply(create_position_elevation, args=(tcx_elt_dict,), axis=1)
    
    # For updating total distance (based on GPX) we assume there is a single lap element
    lap_elt = tcx_tkp_parent.get(tcx_tkp[0])
    if lap_elt is not None:
        lap_elt.text = str(total_dist)
        
    tcx.write('out.tcx',
               xml_declaration=True,
               encoding='UTF-8',
               method='xml',
               short_empty_elements=False)

if __name__ == '__main__':
    main()