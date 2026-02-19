"""
Flask web application for JAIBird Stock Trading Platform.
Provides web interface for managing watchlist and viewing SENS announcements.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

from ..database.models import DatabaseManager, Company
from ..utils.config import get_config
from ..notifications.notifier import NotificationManager
from ..scrapers.sens_scraper import SensScraper
from ..utils.dropbox_manager import DropboxManager
from ..analytics.sens_categorizer import (
    categorize_announcements,
    get_top_companies,
    get_category_breakdown,
    get_noise_summary,
    get_volume_over_time,
    get_urgency_breakdown,
    get_recent_strategic_highlights,
    get_company_activity_heatmap,
    get_all_categories,
    get_today_strategic,
    get_director_dealing_signal,
    get_unusual_activity_alerts,
    get_watchlist_pulse,
    get_sentiment_summary,
    get_upcoming_events,
    get_sector_breakdown,
)
from ..services.price_service import PriceService
from ..company.company_db import CompanyDB


logger = logging.getLogger(__name__)


class CompanyForm(FlaskForm):
    """Form for adding/editing companies."""
    name = StringField('Company Name', validators=[DataRequired(), Length(min=2, max=100)])
    jse_code = StringField('JSE Code', validators=[DataRequired(), Length(min=2, max=10)])
    notes = TextAreaField('Notes', validators=[Length(max=500)])
    submit = SubmitField('Add Company')


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    config = get_config()
    app.config['SECRET_KEY'] = config.flask_secret_key
    app.config['WTF_CSRF_ENABLED'] = True
    
    # Initialize components
    db_manager = DatabaseManager(config.database_path)
    notification_manager = NotificationManager(db_manager)
    
    @app.route('/')
    def index():
        """Home page with dashboard."""
        try:
            # Get recent SENS announcements
            recent_sens = db_manager.get_recent_sens(days=7)
            
            # Get watchlist companies
            watchlist_companies = db_manager.get_all_companies(active_only=True)
            
            # Get database stats
            stats = db_manager.get_database_stats()
            
            return render_template('index.html',
                                 recent_sens=recent_sens[:10],  # Show latest 10
                                 watchlist_companies=watchlist_companies,
                                 stats=stats)
        except Exception as e:
            logger.error(f"Error loading dashboard: {e}")
            flash(f"Error loading dashboard: {e}", 'error')
            return render_template('index.html', recent_sens=[], watchlist_companies=[], stats={})
    
    @app.route('/watchlist')
    def watchlist():
        """Watchlist management page."""
        try:
            companies = db_manager.get_all_companies(active_only=True)
            return render_template('watchlist.html', companies=companies)
        except Exception as e:
            logger.error(f"Error loading watchlist: {e}")
            flash(f"Error loading watchlist: {e}", 'error')
            return render_template('watchlist.html', companies=[])

    @app.route('/prices')
    def prices_page():
        """Stock prices page."""
        try:
            watchlist_codes = [
                c.jse_code.upper()
                for c in db_manager.get_all_companies(active_only=True)
                if c.jse_code
            ]
            return render_template('prices.html', watchlist_codes=watchlist_codes)
        except Exception as e:
            logger.error(f"Error loading prices page: {e}")
            flash(f"Error loading prices page: {e}", 'error')
            return render_template('prices.html', watchlist_codes=[])
    
    @app.route('/add_company', methods=['GET', 'POST'])
    def add_company():
        """Add company to watchlist."""
        form = CompanyForm()
        
        if form.validate_on_submit():
            try:
                # Check if company already exists
                existing = db_manager.get_company_by_jse_code(form.jse_code.data.upper())
                if existing:
                    flash(f'Company with JSE code {form.jse_code.data.upper()} already exists!', 'warning')
                else:
                    company = Company(
                        name=form.name.data,
                        jse_code=form.jse_code.data.upper(),
                        notes=form.notes.data
                    )
                    db_manager.add_company(company)
                    flash(f'Successfully added {company.name} to watchlist!', 'success')
                    return redirect(url_for('watchlist'))
            except Exception as e:
                logger.error(f"Error adding company: {e}")
                flash(f'Error adding company: {e}', 'error')
        
        return render_template('add_company.html', form=form)
    
    @app.route('/remove_company/<jse_code>')
    def remove_company(jse_code):
        """Remove company from watchlist."""
        try:
            if db_manager.deactivate_company(jse_code):
                flash(f'Successfully removed company {jse_code} from watchlist!', 'success')
            else:
                flash(f'Company {jse_code} not found!', 'warning')
        except Exception as e:
            logger.error(f"Error removing company: {e}")
            flash(f'Error removing company: {e}', 'error')
        
        return redirect(url_for('watchlist'))
    
    @app.route('/sens')
    def sens_list():
        """SENS announcements list."""
        try:
            page = request.args.get('page', 1, type=int)
            days = request.args.get('days', 7, type=int)
            
            sens_announcements = db_manager.get_recent_sens(days=days)
            
            # Simple pagination
            per_page = 20
            start = (page - 1) * per_page
            end = start + per_page
            paginated_sens = sens_announcements[start:end]
            
            has_prev = page > 1
            has_next = len(sens_announcements) > end
            
            return render_template('sens_list.html',
                                 sens_announcements=paginated_sens,
                                 page=page,
                                 days=days,
                                 has_prev=has_prev,
                                 has_next=has_next,
                                 total=len(sens_announcements))
        except Exception as e:
            logger.error(f"Error loading SENS list: {e}")
            flash(f"Error loading SENS announcements: {e}", 'error')
            return render_template('sens_list.html', sens_announcements=[], page=1, days=7,
                                 has_prev=False, has_next=False, total=0)
    
    @app.route('/settings')
    def settings():
        """Settings page."""
        try:
            # Get Dropbox storage info
            dropbox_manager = DropboxManager()
            storage_info = dropbox_manager.get_storage_usage()
            
            return render_template('settings.html',
                                 config=config,
                                 storage_info=storage_info)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            flash(f"Error loading settings: {e}", 'error')
            return render_template('settings.html', config=config, storage_info={})
    
    @app.route('/api/scrape', methods=['POST'])
    def api_scrape():
        """Queue a SENS scrape via the scheduler container.

        The web container only has 256 MB – far too little to launch
        Chromium.  Instead we write a trigger file into the shared
        data/ volume.  The scheduler container polls for this file and
        executes the heavy scrape in its own 1.5 GB memory space.
        """
        import json
        trigger_path = Path('data/scrape_trigger.json')
        try:
            trigger_path.write_text(json.dumps({
                'requested_at': datetime.now().isoformat(),
                'source': 'web_dashboard',
            }))
            logger.info("Scrape trigger file written – scheduler will pick it up shortly")
            return jsonify({
                'status': 'success',
                'message': 'Scrape queued – the scheduler will run it within 30 seconds. '
                           'New announcements will appear on the dashboard automatically.',
                'count': 0,
            })
        except Exception as e:
            logger.error(f"Failed to write scrape trigger: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e),
            }), 500
    
    @app.route('/api/test_notifications', methods=['POST'])
    def api_test_notifications():
        """API endpoint to test notification systems."""
        try:
            results = notification_manager.test_notifications()
            return jsonify({
                'status': 'success',
                'results': results
            })
        except Exception as e:
            logger.error(f"API test notifications error: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    @app.route('/api/send_digest', methods=['POST'])
    def api_send_digest():
        """API endpoint to send daily digest."""
        try:
            success = notification_manager.send_daily_digest()
            return jsonify({
                'status': 'success' if success else 'error',
                'message': 'Daily digest sent successfully' if success else 'Failed to send daily digest'
            })
        except Exception as e:
            logger.error(f"API send digest error: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    @app.route('/api/stats')
    def api_stats():
        """API endpoint to get database statistics."""
        try:
            stats = db_manager.get_database_stats()
            return jsonify(stats)
        except Exception as e:
            logger.error(f"API stats error: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/toggle_telegram', methods=['POST'])
    def api_toggle_telegram():
        """API endpoint to toggle Telegram notifications for a company."""
        try:
            data = request.get_json()
            
            if not data or 'jse_code' not in data or 'send_telegram' not in data:
                return jsonify({
                    'status': 'error',
                    'error': 'Missing required fields: jse_code, send_telegram'
                }), 400
            
            jse_code = data['jse_code']
            send_telegram = data['send_telegram']
            
            # Update the company's Telegram flag
            success = db_manager.update_company_telegram_flag(jse_code, send_telegram)
            
            if success:
                action = "enabled" if send_telegram else "disabled"
                return jsonify({
                    'status': 'success',
                    'message': f'Telegram notifications {action} for {jse_code}'
                })
            else:
                return jsonify({
                    'status': 'error',
                    'error': f'Company with JSE code {jse_code} not found'
                }), 404
                
        except Exception as e:
            logger.error(f"API toggle telegram error: {e}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500
    
    # ====================================================================
    # EXECUTIVE DASHBOARD API ENDPOINTS
    # ====================================================================

    def _get_categorised_sens(days: Optional[int] = None):
        """Helper: fetch and categorise SENS announcements."""
        if days:
            announcements = db_manager.get_recent_sens(days=days)
        else:
            announcements = db_manager.get_all_sens_announcements()
        return categorize_announcements(announcements)

    @app.route('/api/dashboard/top_companies')
    def api_dashboard_top_companies():
        """Top N companies by SENS announcement volume."""
        try:
            n = request.args.get('n', 10, type=int)
            days = request.args.get('days', None, type=int)
            exclude_noise = request.args.get('exclude_noise', 'false').lower() == 'true'
            categorised = _get_categorised_sens(days)
            data = get_top_companies(categorised, n=n, exclude_noise=exclude_noise)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard top_companies error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/category_breakdown')
    def api_dashboard_category_breakdown():
        """SENS announcements grouped by thematic category."""
        try:
            days = request.args.get('days', None, type=int)
            exclude_noise = request.args.get('exclude_noise', 'true').lower() == 'true'
            categorised = _get_categorised_sens(days)
            data = get_category_breakdown(categorised, exclude_noise=exclude_noise)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard category_breakdown error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/noise_summary')
    def api_dashboard_noise_summary():
        """Strategic vs noise announcement split."""
        try:
            days = request.args.get('days', None, type=int)
            categorised = _get_categorised_sens(days)
            data = get_noise_summary(categorised)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard noise_summary error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/volume_over_time')
    def api_dashboard_volume_over_time():
        """SENS volume bucketed by day/week/month."""
        try:
            bucket = request.args.get('bucket', 'day')
            days = request.args.get('days', 30, type=int)
            exclude_noise = request.args.get('exclude_noise', 'false').lower() == 'true'
            categorised = _get_categorised_sens(days)
            data = get_volume_over_time(categorised, bucket=bucket, exclude_noise=exclude_noise)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard volume_over_time error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/urgency')
    def api_dashboard_urgency():
        """Urgent vs normal announcement breakdown."""
        try:
            days = request.args.get('days', None, type=int)
            categorised = _get_categorised_sens(days)
            data = get_urgency_breakdown(categorised)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard urgency error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/strategic_highlights')
    def api_dashboard_strategic_highlights():
        """Most recent strategic (non-noise) announcements."""
        try:
            n = request.args.get('n', 8, type=int)
            days = request.args.get('days', 7, type=int)
            categorised = _get_categorised_sens(days)
            data = get_recent_strategic_highlights(categorised, n=n)
            # Serialize datetimes
            for item in data:
                if item.get('date_published'):
                    item['date_published'] = item['date_published'].isoformat()
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard strategic_highlights error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/company_heatmap')
    def api_dashboard_company_heatmap():
        """Category-by-company activity heatmap for top companies."""
        try:
            n = request.args.get('n', 10, type=int)
            days = request.args.get('days', None, type=int)
            categorised = _get_categorised_sens(days)
            data = get_company_activity_heatmap(categorised, top_n=n)
            return jsonify({'status': 'success', 'data': data})
        except Exception as e:
            logger.error(f"Dashboard company_heatmap error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/categories')
    def api_dashboard_categories():
        """Return the full category taxonomy."""
        try:
            return jsonify({'status': 'success', 'data': get_all_categories()})
        except Exception as e:
            logger.error(f"Dashboard categories error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/dashboard/full')
    def api_dashboard_full():
        """
        Single endpoint returning all dashboard data in one call.
        Each section is independently try/excepted so a single failure
        doesn't take down the whole dashboard.
        """
        def _safe(label, fn, default=None):
            """Run fn, returning default on error."""
            try:
                return fn()
            except Exception as e:
                logger.error(f"Dashboard section '{label}' failed: {e}")
                return default if default is not None else {}

        def _serialize_dates(items, key='date_published'):
            """In-place convert datetime objects to ISO strings."""
            for item in items:
                if item.get(key) and hasattr(item[key], 'isoformat'):
                    item[key] = item[key].isoformat()
            return items

        try:
            days = request.args.get('days', None, type=int)
            categorised = _get_categorised_sens(days)

            # Recent 7-day set for highlights
            recent_categorised = _get_categorised_sens(7) if (days and days > 7) else categorised

            # Volume – last 30 days
            vol_categorised = _get_categorised_sens(30) if (days is None or days > 30) else categorised

            # --- Phase 1 core (these are all fast, pure-Python) ---
            noise = get_noise_summary(categorised)
            highlights = _serialize_dates(get_recent_strategic_highlights(recent_categorised, n=8))

            result = {
                'top_companies': get_top_companies(categorised, n=10, exclude_noise=False),
                'top_companies_strategic': get_top_companies(categorised, n=10, exclude_noise=True),
                'category_breakdown': get_category_breakdown(categorised, exclude_noise=True),
                'category_breakdown_all': get_category_breakdown(categorised, exclude_noise=False),
                'noise_summary': noise,
                'volume_by_day': get_volume_over_time(vol_categorised, bucket='day'),
                'volume_by_week': get_volume_over_time(categorised, bucket='week'),
                'urgency': get_urgency_breakdown(categorised),
                'strategic_highlights': highlights,
                'company_heatmap': _safe('heatmap', lambda: get_company_activity_heatmap(categorised, top_n=10)),
            }

            # --- Phase 2: Each section independently protected ---

            # Today ticker
            result['today_strategic'] = _safe('today', lambda: _serialize_dates(
                get_today_strategic(categorised)), [])

            # Director dealing signal
            def _director():
                ds = get_director_dealing_signal(categorised)
                for k in ('recent_buys', 'recent_sells'):
                    _serialize_dates(ds.get(k, []))
                return ds
            result['director_signal'] = _safe('director_signal', _director)

            # Unusual activity
            result['unusual_alerts'] = _safe('unusual_alerts', lambda:
                get_unusual_activity_alerts(categorised), [])

            # Watchlist pulse
            def _pulse():
                wl = db_manager.get_all_companies(active_only=True)
                return get_watchlist_pulse(categorised, [c.name for c in wl])
            result['watchlist_pulse'] = _safe('watchlist_pulse', _pulse)

            # Sentiment (lightweight query — no pdf_content loaded)
            def _sentiment():
                summaries = db_manager.get_sens_summaries_lightweight(days=days)
                return get_sentiment_summary(summaries)
            result['sentiment'] = _safe('sentiment', _sentiment)

            # Watchlist summary cards
            result['watchlist_summaries'] = _safe('watchlist_summaries', lambda:
                db_manager.get_watchlist_summaries(), [])

            # Events / calendar
            result['upcoming_events'] = _safe('events', lambda:
                _serialize_dates(get_upcoming_events(categorised), key='date'), [])

            # Sector breakdown
            result['sector_breakdown'] = _safe('sectors', lambda:
                get_sector_breakdown(categorised, exclude_noise=True), [])

            # Stock price data
            result['price_movers'] = _safe('price_movers', lambda:
                price_service.get_movers(n=5), {'gainers': [], 'losers': []})
            result['price_momentum'] = _safe('price_momentum', lambda:
                price_service.get_momentum_report(), [])

            # Scrape health status
            def _health():
                return {
                    'last_scrape_time': db_manager.get_config_value('last_scrape_time', ''),
                    'last_scrape_status': db_manager.get_config_value('last_scrape_status', 'unknown'),
                    'consecutive_failures': int(
                        db_manager.get_config_value('consecutive_scrape_failures', '0')),
                    'last_fail_time': db_manager.get_config_value('last_scrape_fail_time', ''),
                }
            result['scrape_health'] = _safe('scrape_health', _health)

            return jsonify({'status': 'success', 'data': result})
        except Exception as e:
            logger.error(f"Dashboard full error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ====================================================================
    # STOCK PRICE API ENDPOINTS
    # ====================================================================

    price_service = PriceService(db_manager)

    @app.route('/api/prices')
    def api_prices():
        """Full latest snapshot of all tracked stock prices."""
        try:
            snapshot = price_service.get_snapshot()
            return jsonify({'status': 'success', 'data': snapshot, 'count': len(snapshot)})
        except Exception as e:
            logger.error(f"Prices API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/prices/<ticker>')
    def api_price_single(ticker):
        """Latest price + 24h history for a single ticker."""
        try:
            ticker = ticker.upper()
            history = db_manager.get_price_history(ticker, hours=24)
            if not history:
                return jsonify({'status': 'error', 'message': f'No data for {ticker}'}), 404
            return jsonify({
                'status': 'success',
                'ticker': ticker,
                'latest': history[0],
                'history': history,
            })
        except Exception as e:
            logger.error(f"Price single API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/prices/movers')
    def api_price_movers():
        """Top gainers and losers by daily change %."""
        try:
            n = request.args.get('n', 5, type=int)
            movers = price_service.get_movers(n=n)
            return jsonify({'status': 'success', 'data': movers})
        except Exception as e:
            logger.error(f"Price movers API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/prices/momentum')
    def api_price_momentum():
        """Stocks on the hot-list with price change since their SENS trigger."""
        try:
            report = price_service.get_momentum_report()
            return jsonify({'status': 'success', 'data': report})
        except Exception as e:
            logger.error(f"Price momentum API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ====================================================================
    # COMPANY INTELLIGENCE ENDPOINTS
    # ====================================================================

    company_db = CompanyDB()

    @app.route('/companies')
    def companies_page():
        """Company intelligence database page."""
        try:
            count = company_db.get_company_count()
            return render_template('companies.html', company_count=count)
        except Exception as e:
            logger.error(f"Error loading companies page: {e}")
            return render_template('companies.html', company_count=0)

    @app.route('/api/companies')
    def api_companies():
        """List all companies (lightweight)."""
        try:
            q = request.args.get('q', '').strip()
            if q:
                data = company_db.search_companies(q)
            else:
                data = company_db.get_all_profiles()
            return jsonify({'status': 'success', 'data': data, 'count': len(data)})
        except Exception as e:
            logger.error(f"Companies API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/companies/<int:company_id>')
    def api_company_detail(company_id):
        """Full detail for a single company."""
        try:
            detail = company_db.get_company_detail(company_id)
            if not detail:
                return jsonify({'status': 'error', 'message': 'Company not found'}), 404
            return jsonify({'status': 'success', 'data': detail})
        except Exception as e:
            logger.error(f"Company detail API error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', error_code=404, error_message="Page not found"), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', error_code=500, error_message="Internal server error"), 500
    
    return app


def run_app():
    """Run the Flask application."""
    config = get_config()
    app = create_app()
    
    logger.info(f"Starting JAIBird web application on {config.flask_host}:{config.flask_port}")
    
    app.run(
        host=config.flask_host,
        port=config.flask_port,
        debug=config.flask_debug
    )


if __name__ == '__main__':
    run_app()
