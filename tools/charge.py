#!/usr/bin/env python3
"""Test avec plusieurs visiteurs en même temps (point 19 de docs/solidite.md). Bibliothèque standard uniquement.

Chaque visiteur virtuel parcourt les pages publiques en boucle, avec ses propres cookies, pendant la durée choisie.
À la fin : nombre de pages servies, erreurs, et temps de réponse (médian, 95 %, maximum) page par page.

    python tools/charge.py                                   # 20 visiteurs, 30 s, sur http://127.0.0.1:8000
    python tools/charge.py --visiteurs 50 --duree 60
    python tools/charge.py --url https://eventlead.ht --visiteurs 10 --invitation /invitation/<uuid>/

Important : la limite de requêtes (point 01) voit tous ces visiteurs comme UNE seule personne (même adresse IP)
et finit par répondre 429. Pour mesurer la vitesse, lancez le serveur avec RATELIMIT_ENABLED=False ;
pour vérifier que la limite fonctionne, laissez-la active et regardez la ligne « 429 ».
Ne lancez jamais un gros test sur le site en ligne aux heures de visite.
"""
import argparse
import http.cookiejar
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict

DEFAULT_PAGES = ["/", "/evenements/", "/billetterie/", "/aide/", "/publicites/", "/connexion/", "/sante/"]


def visitor(base, pages, stop_at, results, lock):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", "EventLead-test-de-charge"), ("Accept-Language", "fr")]
    i = 0
    while time.time() < stop_at:
        page = pages[i % len(pages)]
        i += 1
        start = time.perf_counter()
        try:
            with opener.open(base + page, timeout=30) as response:
                response.read()
                code = response.status
        except urllib.error.HTTPError as error:
            code = error.code
        except Exception as error:  # délai dépassé, connexion refusée...
            code = type(error).__name__
        elapsed = (time.perf_counter() - start) * 1000
        with lock:
            results[page].append((code, elapsed))


def percentile(values, pct):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(pct / 100 * (len(values) - 1))))]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--visiteurs", type=int, default=20)
    parser.add_argument("--duree", type=int, default=30, help="secondes")
    parser.add_argument("--invitation", default="", help="adresse d'un lien d'invitation à ajouter au parcours")
    parser.add_argument("--max-p95", type=float, default=2000, help="temps (ms) au-delà duquel le test échoue")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    pages = DEFAULT_PAGES + ([args.invitation] if args.invitation else [])
    results, lock = defaultdict(list), threading.Lock()
    print(f"{args.visiteurs} visiteurs en même temps pendant {args.duree} s sur {base} ...")
    stop_at = time.time() + args.duree
    threads = [threading.Thread(target=visitor, args=(base, pages[i % len(pages):] + pages[:i % len(pages)], stop_at, results, lock))
               for i in range(args.visiteurs)]
    started = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration = time.time() - started

    total = errors = limited = 0
    all_times = []
    print(f"\n{'page':<28}{'pages':>7}{'erreurs':>9}{'médian':>9}{'95 %':>9}{'max':>9}  (ms)")
    for page in pages:
        rows = results.get(page, [])
        if not rows:
            continue
        times = [ms for _, ms in rows]
        bad = sum(1 for code, _ in rows if code != 200 and code != 429)
        limited += sum(1 for code, _ in rows if code == 429)
        total += len(rows)
        errors += bad
        all_times += times
        print(f"{page[:27]:<28}{len(rows):>7}{bad:>9}{statistics.median(times):>9.0f}{percentile(times, 95):>9.0f}{max(times):>9.0f}")
    codes = defaultdict(int)
    for rows in results.values():
        for code, _ in rows:
            codes[code] += 1
    print(f"\nTotal : {total} pages en {duration:.0f} s ({total / duration:.1f} par seconde)")
    print("Réponses : " + ", ".join(f"{code} x {n}" for code, n in sorted(codes.items(), key=lambda kv: str(kv[0]))))
    if limited:
        print(f"429 : {limited} réponses « trop de demandes » (la limite de requêtes par visiteur a fonctionné).")
    p95 = percentile(all_times, 95) if all_times else 0
    ok = total > 0 and errors <= total * 0.01 and p95 <= args.max_p95
    print(("RÉSULTAT : OK" if ok else "RÉSULTAT : À REVOIR") + f" (erreurs {errors}/{total}, 95 % des pages en moins de {p95:.0f} ms)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
