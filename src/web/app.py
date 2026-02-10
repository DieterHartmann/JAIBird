"""
Flask web application for JAIBird Stock Trading Platform.
Provides web interface for managing watchlist and viewing SENS announcements.
"""

import logging
from datetime import datetime
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
)


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
        """API endpoint to trigger SENS scraping with AI parsing and notifications."""
        try:
            from ..ai.pdf_parser import parse_sens_announcement
            from ..utils.dropbox_manager import DropboxManager

            scraper = SensScraper(db_manager)
            announcements = scraper.scrape_daily_announcements()

            dropbox_manager = DropboxManager()
            # Company enrichment
            from ..company.enricher import CompanyEnricher
            from ..company.company_db import CompanyDB
            enricher = CompanyEnricher(CompanyDB())
            processed = 0

            # Process AI parsing, upload, and notifications for new announcements
            for announcement in announcements:
                try:
                    # Parse PDF and generate AI summary for ALL new announcements
                    parsed = parse_sens_announcement(announcement)
                    if getattr(parsed, 'ai_summary', None):
                        # Persist parsing results via model-aware helper
                        announcement.pdf_content = getattr(parsed, 'pdf_content', '')
                        announcement.ai_summary = parsed.ai_summary
                        announcement.parse_method = getattr(parsed, 'parse_method', '')
                        announcement.parse_status = getattr(parsed, 'parse_status', 'completed')
                        announcement.parsed_at = getattr(parsed, 'parsed_at', None)
                        db_manager.update_sens_parsing(announcement)

                    # Upload to Dropbox if available
                    if announcement.local_pdf_path:
                        dropbox_path = dropbox_manager.upload_pdf(
                            announcement.local_pdf_path,
                            announcement.sens_number,
                            announcement.company_name
                        )
                        if dropbox_path:
                            announcement.dropbox_pdf_path = dropbox_path

                    # Send notifications
                    notification_manager.process_new_announcement(announcement)

                    # Enrich company intelligence DB
                    enricher.enrich_from_announcement(announcement)
                    processed += 1
                except Exception as inner_e:
                    logger.error(f"Failed to process new announcement {announcement.sens_number}: {inner_e}")

            return jsonify({
                'status': 'success',
                'message': f'Successfully scraped {len(announcements)} new announcements',
                'count': len(announcements),
                'processed': processed
            })
        except Exception as e:
            logger.error(f"API scrape error: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
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
        Avoids multiple round-trips from the frontend.
        """
        try:
            days = request.args.get('days', None, type=int)
            categorised = _get_categorised_sens(days)

            # Also get recent 7-day set for highlights
            if days and days > 7:
                recent_categorised = _get_categorised_sens(7)
            else:
                recent_categorised = categorised

            # Volume over time – last 30 days by day
            vol_categorised = _get_categorised_sens(30)

            noise = get_noise_summary(categorised)
            highlights = get_recent_strategic_highlights(recent_categorised, n=8)
            for item in highlights:
                if item.get('date_published'):
                    item['date_published'] = item['date_published'].isoformat()

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
                'company_heatmap': get_company_activity_heatmap(categorised, top_n=10),
            }

            return jsonify({'status': 'success', 'data': result})
        except Exception as e:
            logger.error(f"Dashboard full error: {e}")
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
