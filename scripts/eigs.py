import sys, os, json
sys.path.append('/Users/benjamin/Desktop/repos/chi-data/backend') 
sys.path.append('/Users/benjamin/Desktop/repos/chi-data/backend/aws') 
from s3 import S3
from dynamo import DynamoConn
import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import s3fs
import decimal
from time import time
from config import cook_tracts, chicago_tracts, msa_tracts
arrow_s3fs = s3fs.S3FileSystem()
s3 = S3()
d = DynamoConn()

boundaries = {
	# 'chicago': chicago_tracts,
	# 'cook': cook_tracts,
	# 'msa': msa_tracts,
	'msa-opposite': msa_tracts
}

stats = {
	'S000': 'total_jobs',
	'SA01': 'age_group_1',
	'SA02': 'age_group_2',
	'SA03': 'age_group_3',
	'SE01': 'salary_group_1',
	'SE02': 'salary_group_2',
	'SE03': 'salary_group_3',
	'SI01': 'industry_group_1',
	'SI02': 'industry_group_2',
	'SI03': 'industry_group_3'
}

dataset_names = {}

for boundary in boundaries:
	for stat in stats:
		dataset_names['eigs-%s-%s' % (boundary, stat)] = {
			'dataset': 'JT00',
			'stat': stat,
			'stat_name': stats[stat],
			'boundaries': boundaries[boundary],
			'boundary': 'msa'
		}

# dataset_names = {
# 	'eigs': {
# 		'dataset': 'JT00',
# 		'stat': 'S000',
# 		'boundaries': chicago_tracts,
# 		'boundary': 'chicago'
# 	},
# 	'eigs-cook': {
# 		'dataset': 'JT00',
# 		'stat': 'S000',
# 		'boundaries': cook_tracts,
# 		'boundary': 'cook'
# 	}
# }
# print dataset_names
for dataset_name in dataset_names:
	all_of_the_keys = {}

	# 14 
	for i in range(14):
		print i
		year = 2002 + i
		# if year >= 2010:
		timea = time()
		print year, dataset_name
		ds = pq.ParquetDataset(
			path_or_paths=[
				'bnroths/chicago-data/lehd_od/year=%s/il_lehd_od_main_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
				'bnroths/chicago-data/lehd_od/year=%s/il_lehd_od_aux_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
				
				'bnroths/chicago-data/lehd_od/year=%s/in_od_main_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
				'bnroths/chicago-data/lehd_od/year=%s/in_od_aux_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
				
				'bnroths/chicago-data/lehd_od/year=%s/wi_od_main_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
				'bnroths/chicago-data/lehd_od/year=%s/wi_od_aux_%s_%s.parquet' % (year, dataset_names[dataset_name]['dataset'], year), 
			
			],
			filesystem=arrow_s3fs, 
			validate_schema=False
		)

		table = ds.read(columns=['w_tract', 'h_tract', dataset_names[dataset_name]['stat']])
		df = table.to_pandas()
		# print 'dataset', dataset_names[dataset_name]
		# print df.shape
		# if dataset_names[dataset_name]['boundary'] in ('chicago', 'cook'):
		# print len(dataset_names[dataset_name]['boundaries'])
		# df = df[df['h_tract'].isin(dataset_names[dataset_name]['boundaries'])]
		# df = df[df['w_tract'].isin(dataset_names[dataset_name]['boundaries'])]
		# print df.shape
		# print df.head()
		# print (set(df.h_tract) - set(df.w_tract))
		# print (set(df.w_tract) - set(df.h_tract))
		diff1 = set(df.h_tract) - set(df.w_tract)
		for tract in diff1:
			df = df[df.h_tract != tract]

		diff2 = set(df.w_tract) - set(df.h_tract)
		for tract in diff2:
			df = df[df.w_tract != tract]

		# print df.head()
		pivot = pd.pivot_table(df, 
			values=dataset_names[dataset_name]['stat'], 
			columns=['h_tract'], 
			index=['w_tract'], 
			aggfunc=np.sum,
			fill_value=0)
		# print pivot.shape
		# print np.isnan(pivot).any()
		# print np.isnan(pivot).any()
		# pivot = pivot.fillna(0)
		# print np.isnan(pivot).any()
		# print np.isnan(pivot).any()
		# print pivot.shape
		# print pivot.head()
		# column totals (w_tract)
		w_tracts = pivot.sum()
		# row totals (h_tracts)
		h_tracts = pivot.transpose().sum()
		A = pivot.transpose()/h_tracts
		A = A.fillna(0).replace([np.inf, -np.inf], 0)

		w, v = np.linalg.eig(A)

		eigs = []
		## eigs may not come back in order so order them real quick
		idx = w.argsort()[::-1]
		eigenValues = w[idx]
		eigenVectors = v[:,idx]
		sub_data = []
		for i in range(10):
			# print i
			eigenvalue_i = i+1
			# val = round(eigenValues[i], 4)
			vector = eigenVectors[:, i]
			if eigenValues[i].imag != 0:
				value = "%s+%si" % (round(eigenValues[i].real, 2), round(eigenValues[i].imag, 2))
			else:
				value = "%s" % (round(eigenValues[i].real, 2))
			# if i == 0:
			# 	print vector
			# 	print vector.min()
			# 	print vector.max()
			

			sub_data.append({
				"name": "Eigenvalue %s" % eigenvalue_i,
				"value": value,
				"key": str(eigenvalue_i)
			})

			if abs(vector.min()) >= abs(vector.max()):
				transformed = [round(-1000*x.real, 1) for x in vector]
			else:
				transformed = [round(1000*x.real, 1) for x in vector]
			imag    	= [round(1000*x.imag, 1) for x in vector]
			has_imag    = [1 if x.imag != 0 else 0 for x in vector]
			# print transformed
			# print has_imag
			eig = {
				"row": i,
				"value": value,
				"vector": transformed,
				"has_imag": has_imag,
				"columns": pivot.columns
			}
			eigs.append(eig)
			tracts = {}
			for i, column in enumerate(pivot.columns):
				tracts[column] = {"real": transformed[i], "imag": imag[i], "has_img": has_imag[i]}
					
			final = {
				"data": tracts,
				"meta": {
					# "max": abs(max(tracts.values(), key=abs)),
					"max": max(tracts.values()),
					"min": min(tracts.values()),
					"top": sorted(tracts.values())[-15]
				}
			}
		
			stat = eigenvalue_i

			with open('%s.json' % stat, 'w') as f:
				f.write(json.dumps(final))

			s3.save_file_public(
				local='%s.json' % stat,
				dataset=dataset_name, 
				dt=year, 
				filename='%s.json' % stat
			)
			os.remove('%s.json' % stat)

			all_of_the_keys["%s" % year] = sub_data


		## update dynamo metadata
		metadata = d.get(dataset=dataset_name)
		timeb = time()
		print timeb - timea
		if not metadata:
			metadata = {
				u'last_updated': u'2018-01-01', 
				u'example_data': u'{}', 
				u'name': u'O-D Eigenvalues %s %s' % (dataset_names[dataset_name]['boundary'], dataset_names[dataset_name]['stat']), 
				u'sub_data': u'[{"name": "Eigenvalue 1", "key": "1"}, {"name": "Eigenvalue 2", "key": "2"}, {"name": "Eigenvalue 3", "key": "3"}, {"name": "Eigenvalue 4", "key": "4"}, {"name": "Eigenvalue 5", "key": "5"}, {"name": "Eigenvalue 6", "key": "6"}, {"name": "Eigenvalue 7", "key": "7"}, {"name": "Eigenvalue 8", "key": "8"}, {"name": "Eigenvalue 9", "key": "9"}, {"name": "Eigenvalue 10", "key": "10"}]', 
				u'dataset': dataset_name, 
				u'source': u'Plenario', 
				u'dataset_long_name': u'311_service_requests_sanitation_code_complaints', 
				u'map_type': u'geojson', 
				u'dataset_start': u'2011-01-01', 
				u'cnts': u'{"2002": 1, "2003": 1, "2006": 1, "2007": 1, "2004": 1, "2005": 1, "2015": 1, "2014": 1, "2008": 1, "2009": 1, "2011": 1, "2010": 1, "2013": 1, "2012": 1}', 
				u'boundary': dataset_names[dataset_name]['boundary'], 
				u'table': None, 
				u'order': 2, 
				u'columns': [None, u'creation_date', u'latitude', u'longitude'], 
				u'description': u'Eigenvector and Values of LEHD Origin Destination dataset of %s' % dataset_names[dataset_name]['stat_name']}
		metadata['table'] = json.dumps(all_of_the_keys)
		d.put_item(metadata)

# print all_of_the_keys
