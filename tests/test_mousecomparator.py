import os
import csv
import tempfile
import unittest
import cv2
import numpy as np

import MouseComparator as mc


class TestMouseComparatorSuite(unittest.TestCase):
    """Comprehensive unit tests for MouseComparator data loading, statistics, visual engines, and exports."""

    def _create_synthetic_export_dir(self, base_dir: str, subject_id: str = "M01", num_runs: int = 3, fault_base: int = 4):
        safe_id = mc.AnalyzerDatasetLoader.make_safe_id(subject_id)
        subj_dir = os.path.join(base_dir, f"subject_{safe_id}")
        os.makedirs(subj_dir, exist_ok=True)

        headers = [
            "Egyed_ID", "Video_Fajl", "Futas_Sorszam", "Irany",
            "Teljes_Athaladasi_Ido_mp", "Netto_Mozgasi_Ido_mp",
            "Melynyulasok_Szama", "Mancs_Labhiba_Db",
            "Mellso_Labhiba_Db", "Hatso_Labhiba_Db",
            "Enyhe_Megcsuszas_Db", "Mely_Leleses_Db",
            "Orr_Lenezes_Db", "Hatso_Farok_Db",
            "Megallasok_Szama", "Megallasok_OsszIdeje_mp",
            "Mikro_Megtorpanas_Db", "Mikro_Megtorpanas_Ido_mp",
            "Sebesseg_Ingadozas_CV", "Mozgas_Darabossag_Jerk",
            "Testtartas_Imbolygas_px", "Bizonytalansagi_Index_Pct",
            "Skala_px_per_cm", "Megtett_Ut_cm", "Atlagsebesseg_cm_mp", "Max_Sebesseg_cm_mp",
            "Start_Zona_Ido_mp", "Start_Lenyulas_Db", "Start_Megallas_Db",
            "Kozep_Zona_Ido_mp", "Kozep_Lenyulas_Db", "Kozep_Megallas_Db",
            "Cel_Zona_Ido_mp", "Cel_Lenyulas_Db", "Cel_Megallas_Db",
        ]
        csv_path = os.path.join(subj_dir, f"egyed_{safe_id}_meresi_adatok.csv")
        with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(headers)
            for r in range(1, num_runs + 1):
                faults = max(0, fault_base - (r - 1))
                transit = 8.5 - 1.2 * (r - 1)
                # Use Hungarian comma decimal format to verify parser resilience
                row = [
                    subject_id, f"{safe_id}_session.mp4", str(r), "FORWARD",
                    f"{transit:.2f}".replace(".", ","), f"{transit - 0.5:.2f}".replace(".", ","),
                    str(faults + 1), str(faults),
                    str(max(0, faults - 1)), str(min(1, faults)),
                    str(faults), "0",
                    "1", "0",
                    "1", "0,50",
                    "2", "0,35",
                    "0,420", "14,2",
                    "3,10", f"{25.0 + faults * 8.0:.1f}".replace(".", ","),
                    "10,0", "60,0", f"{60.0 / transit:.2f}".replace(".", ","), "22,5",
                    "2,5", "1", "0",
                    "3,5", str(max(0, faults - 1)), "1",
                    "2,5", "0", "0",
                ]
                writer.writerow(row)

                # Create synthetic heatmap, summary, and dip crop images
                hm = np.zeros((240, 640, 3), dtype=np.uint8)
                cv2.circle(hm, (120 + r * 80, 120), 45, (0, 140, 255), -1)
                mc.save_image_unicode(os.path.join(subj_dir, f"egyed_{safe_id}_futas_{r}_heatmap.jpg"), hm)
                mc.save_image_unicode(os.path.join(subj_dir, f"egyed_{safe_id}_futas_{r}_halvany_heatmap.jpg"), hm)
                mc.save_image_unicode(os.path.join(subj_dir, f"egyed_{safe_id}_futas_{r}_osszefoglalo.jpg"), hm)
                if faults > 0:
                    dip_im = np.full((160, 220, 3), (40, 40, 180), dtype=np.uint8)
                    mc.save_image_unicode(os.path.join(subj_dir, f"egyed_{safe_id}_futas_{r}_lenyulas_1.jpg"), dip_im)

        comb = np.zeros((240, 640, 3), dtype=np.uint8)
        cv2.circle(comb, (320, 120), 60, (20, 200, 255), -1)
        mc.save_image_unicode(os.path.join(subj_dir, f"egyed_{safe_id}_OSSZESITETT_heatmap.jpg"), comb)
        return subj_dir

    def test_loader_discovers_csv_and_linked_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_synthetic_export_dir(tmp, subject_id="Mouse_A1", num_runs=3, fault_base=4)
            records = mc.AnalyzerDatasetLoader.load_from_path(tmp)
            self.assertEqual(len(records), 3)
            r1 = records[0]
            self.assertEqual(r1.subject_id, "Mouse_A1")
            self.assertAlmostEqual(r1.metrics["Teljes_Athaladasi_Ido_mp"], 8.50, places=2)
            self.assertEqual(r1.metrics["Mancs_Labhiba_Db"], 4.0)
            self.assertTrue(os.path.isfile(r1.heatmap_path))
            self.assertTrue(os.path.isfile(r1.summary_img_path))
            self.assertTrue(os.path.isfile(r1.combined_heatmap_path))
            self.assertEqual(len(r1.dip_crop_paths), 1)

            aggs = mc.AnalyzerDatasetLoader.build_subject_aggregates(records)
            self.assertEqual(len(aggs), 1)
            self.assertTrue(aggs[0].is_subject_aggregate)
            self.assertAlmostEqual(aggs[0].metrics["Mancs_Labhiba_Db"], 3.0, places=2)

    def test_statistical_1v1_and_cohort_and_longitudinal(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_a = os.path.join(tmp, "group_control")
            dir_b = os.path.join(tmp, "group_treated")
            self._create_synthetic_export_dir(dir_a, subject_id="C01", num_runs=3, fault_base=6)
            self._create_synthetic_export_dir(dir_b, subject_id="T01", num_runs=3, fault_base=1)

            recs_a = mc.AnalyzerDatasetLoader.load_from_path(dir_a)
            recs_b = mc.AnalyzerDatasetLoader.load_from_path(dir_b)

            # 1v1 comparison
            rows_1v1 = mc.StatisticalComparator.compare_1v1(recs_a[0], recs_b[0], lang="en")
            fault_row = next(r for r in rows_1v1 if r["key"] == "Mancs_Labhiba_Db")
            self.assertEqual(fault_row["val_a"], 6.0)
            self.assertEqual(fault_row["val_b"], 1.0)
            self.assertEqual(fault_row["delta"], -5.0)
            self.assertEqual(fault_row["status"], "improved")

            # Cohort comparison
            rows_coh = mc.StatisticalComparator.compare_cohorts(recs_a, recs_b, lang="en")
            coh_fault = next(r for r in rows_coh if r["key"] == "Mancs_Labhiba_Db")
            self.assertLess(coh_fault["val_b"], coh_fault["val_a"])
            self.assertLess(coh_fault["p_t"], 0.05)
            self.assertLess(coh_fault["cohens_d"], -1.5)

            # Longitudinal trend
            trend = mc.StatisticalComparator.compute_longitudinal_trend(recs_a, "Mancs_Labhiba_Db")
            self.assertAlmostEqual(trend["slope"], -1.0, places=3)
            self.assertLess(trend["pct_change"], 0.0)

    def test_visual_comparison_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._create_synthetic_export_dir(tmp, subject_id="M01", num_runs=2, fault_base=3)
            recs = mc.AnalyzerDatasetLoader.load_from_path(tmp)
            im_a = mc.read_image_unicode(recs[0].heatmap_path)
            im_b = mc.read_image_unicode(recs[1].heatmap_path)

            spat = mc.VisualComparisonEngine.compute_spatial_metrics(im_a, im_b)
            self.assertIn("ssim", spat)
            self.assertGreater(spat["ssim"], 0.1)

            sbs = mc.VisualComparisonEngine.render_side_by_side(im_a, im_b, "Run 1", "Run 2")
            wipe = mc.VisualComparisonEngine.render_wipe_slider(im_a, im_b, 0.4, "Run 1", "Run 2")
            diff = mc.VisualComparisonEngine.render_difference_heatmap(im_a, im_b, "Run 1", "Run 2")
            blend = mc.VisualComparisonEngine.render_onion_blend(im_a, im_b, 0.5, "Run 1", "Run 2")
            radar = mc.VisualComparisonEngine.render_radar_and_zones_chart(recs[0].metrics, recs[1].metrics)
            long_ch = mc.VisualComparisonEngine.render_longitudinal_chart(recs, "Teljes_Athaladasi_Ido_mp")
            dips_gal = mc.VisualComparisonEngine.render_dip_gallery(recs[0], recs[1])

            for rendered in (sbs, wipe, diff, blend, radar, long_ch, dips_gal):
                self.assertIsNotNone(rendered)
                self.assertEqual(rendered.ndim, 3)
                self.assertGreater(rendered.shape[0], 100)
                self.assertGreater(rendered.shape[1], 200)

            rows = mc.StatisticalComparator.compare_1v1(recs[0], recs[1], lang="en")
            comp_img = mc.ReportExporter.build_composite_summary_image(sbs, diff, radar, rows, "Run 1", "Run 2")
            img_out = os.path.join(tmp, "summary.png")
            self.assertTrue(mc.save_image_unicode(img_out, comp_img))
            self.assertTrue(os.path.isfile(img_out))

            csv_out = os.path.join(tmp, "deltas.csv")
            self.assertTrue(mc.ReportExporter.export_csv(csv_out, rows, is_cohort=False))
            self.assertTrue(os.path.isfile(csv_out))

            html_out = os.path.join(tmp, "report.html")
            self.assertTrue(
                mc.ReportExporter.export_html_report(
                    html_out, "Run 1", "Run 2", rows, spat, sbs, diff, radar, is_cohort=False
                )
            )
            self.assertTrue(os.path.isfile(html_out))

    def test_paired_cohort_aggregation_and_origin_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_a = os.path.join(tmp, "healthy")
            dir_b = os.path.join(tmp, "sick")
            # Create 5 matched subjects in A and B
            recs_a = []
            recs_b = []
            for idx in range(1, 6):
                sid = f"S{idx:02d}"
                self._create_synthetic_export_dir(dir_a, subject_id=sid, num_runs=3, fault_base=1)
                self._create_synthetic_export_dir(dir_b, subject_id=sid, num_runs=3, fault_base=5 + idx)
            recs_a = mc.AnalyzerDatasetLoader.load_from_path(dir_a)
            recs_b = mc.AnalyzerDatasetLoader.load_from_path(dir_b)

            # Inject a Run-3 motivation-loss outlier in A for S01 (transit = 45.0s on Run 3)
            for r in recs_a:
                if r.subject_id == "S01" and r.run_num == 3:
                    r.metrics["Teljes_Athaladasi_Ido_mp"] = 45.0

            agg_med = mc.StatisticalComparator.aggregate_subject_runs(recs_a, agg_mode="median")
            agg_mean = mc.StatisticalComparator.aggregate_subject_runs(recs_a, agg_mode="mean")
            self.assertLess(agg_med["S01"]["Teljes_Athaladasi_Ido_mp"], 10.0)
            self.assertGreater(agg_mean["S01"]["Teljes_Athaladasi_Ido_mp"], 18.0)

            rows_paired = mc.StatisticalComparator.compare_cohorts(
                recs_a, recs_b, lang="hu", paired=True, agg_mode="median", aggregate_by_subject=True
            )
            fault_row = next(r for r in rows_paired if r["key"] == "Mancs_Labhiba_Db")
            self.assertEqual(fault_row["n_a"], 5)
            self.assertEqual(fault_row["n_b"], 5)
            self.assertTrue(fault_row["paired"])
            self.assertIn(fault_row["rec_test"], ("Paired t-test", "Wilcoxon"))
            self.assertLess(fault_row["p_rec"], 0.05)

            trial_res = mc.StatisticalComparator.analyze_trial_effect(recs_a)
            self.assertGreater(len(trial_res), 0)
            self.assertEqual(trial_res[0]["n_subjects"], 5)

            origin_dir = os.path.join(tmp, "origin_pkg")
            written = mc.ReportExporter.export_origin_package(
                origin_dir, recs_a, recs_b, agg_mode="median", paired=True, lang="hu"
            )
            self.assertEqual(len(written), 4)
            for p in written:
                self.assertTrue(os.path.isfile(p))
            with open(os.path.join(origin_dir, "Origin_Wide_Paired_median.csv"), "r", encoding="utf-8-sig") as f:
                lines = f.read().strip().splitlines()
                self.assertEqual(len(lines), 6)  # 1 header + 5 matched subjects


if __name__ == "__main__":
    unittest.main()
