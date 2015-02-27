# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Yannick Buron
#    Copyright 2013 Yannick Buron
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp import modules

class ClouderApplicationVersion(models.Model):
    _inherit = 'clouder.application.version'

    @api.multi
    def build_application(self):
        super(ClouderApplicationVersion, self).build_application()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.archive_id.fullname())
            self.execute(ssh, ['apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -y -qq install git php-pear'])
            self.execute(ssh, ['pear channel-discover pear.drush.org'])
            self.execute(ssh, ['pear install drush/drush'])
            self.execute(ssh, ['echo "' + self.application_id.buildfile.replace('"', '\\"') + '" >> ' + self.full_archivepath() + '/drush.make'])
            self.execute(ssh, ['drush', 'make', self.full_archivepath() + '/drush.make', './'], path=self.full_archivepath())
            self.execute(ssh, ['mv', self.full_archivepath() + '/sites', self.full_archivepath() + '/sites-template'])
            self.execute(ssh, ['ln', '-s', '../sites', self.full_archivepath() + '/sites'])
            ssh.close(), sftp.close()


        return


    @api.multi
    def get_current_version(self):

        return False




class ClouderService(models.Model):
    _inherit = 'clouder.service'


    @api.multi
    def deploy_post_service(self):
        super(ClouderService, self).deploy_post_service()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['cp', '-R', self.full_localpath_files() + '/sites-template', self.full_localpath() + '/sites'])
            ssh.close(), sftp.close()

        return


class ClouderBase(models.Model):
    _inherit = 'clouder.base'

    @api.multi
    def deploy_build(self):
        res = super(ClouderBase, self).deploy_build()
        if self.application_id.type_id.name == 'drupal':

            ssh, sftp = self.connect(self.service_id.container_id.fullname())
            config_file = '/etc/nginx/sites-available/' + self.fullname()
            sftp.put(modules.get_module_path('clouder_drupal') + '/res/nginx.config', config_file)
            self.execute(ssh, ['sed', '-i', '"s/BASE/' + self.name + '/g"', config_file])
            self.execute(ssh, ['sed', '-i', '"s/DOMAIN/' + self.domain_id.name + '/g"', config_file])
            self.execute(ssh, ['sed', '-i', '"s/PATH/' + self.service_id.full_localpath_files().replace('/','\/') + '/g"', config_file])
            self.execute(ssh, ['ln', '-s',  '/etc/nginx/sites-available/' + self.fullname(),  '/etc/nginx/sites-enabled/' + self.fullname()])
            self.execute(ssh, ['/etc/init.d/nginx','reload'])
            ssh.close(), sftp.close()
            #
            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['drush', '-y', 'si',
                                  '--db-url=' + self.service_id.database_type() + '://' + self.service_id.db_user() + ':' + self.service_id.database_password + '@' + self.service_id.database_server() + '/' + self.unique_name_(),
                                  '--account-mail=' + self.admin_email,
                                  '--account-name=' + self.admin_name,
                                  '--account-pass=' + self.admin_password,
                                  '--sites-subdir=' + self.fulldomain(),
                                  'minimal'], path=self.service_id.full_localpath_files())

            if self.application_id.options()['install_modules']['value']:
                modules = self.application_id.options()['install_modules']['value'].split(',')
                for module in modules:
                    self.execute(ssh, ['drush', '-y', 'en', module], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            if self.application_id.options()['theme']['value']:
                theme = self.application_id.options()['theme']['value']
                self.execute(ssh, ['drush', '-y', 'pm-enable', theme], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
                self.execute(ssh, ['drush', 'vset', '--yes', '--exact', 'theme_default', theme], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            ssh.close(), sftp.close()


  # drush vset --yes --exact bakery_master $bakery_master_site
  # drush vset --yes --exact bakery_key '$bakery_private_key'
  # drush vset --yes --exact bakery_domain $bakery_cookie_domain

        return res

# post restore
#     ssh $system_user@$server << EOF
#       mkdir $instances_path/$instance/sites/$clouder.$domain
#       cp -r $instances_path/$instance/$db_type/sites/* $instances_path/$instance/sites/$clouder.$domain/
#       cd $instances_path/$instance/sites/$clouder.$domain
#       sed -i "s/'database' => '[#a-z0-9_!]*'/'database' => '$unique_name_underscore'/g" $instances_path/$instance/sites/$clouder.$domain/settings.php
#       sed -i "s/'username' => '[#a-z0-9_!]*'/'username' => '$db_user'/g" $instances_path/$instance/sites/$clouder.$domain/settings.php
#       sed -i "s/'password' => '[#a-z0-9_!]*'/'password' => '$database_passwpord'/g" $instances_path/$instance/sites/$clouder.$domain/settings.php
#       sed -i "s/'host' => '[0-9.]*'/'host' => '$database_server'/g" $instances_path/$instance/sites/$clouder.$domain/settings.php
#       pwd
#       echo Title $title
#       drush vset --yes --exact site_name $title
#       drush user-password $admin_user --password=$admin_password
# EOF
#

    @api.multi
    def deploy_post(self):
        res = super(ClouderBase, self).deploy_post()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['drush', 'vset', '--yes', '--exact', 'site_name', self.title], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            ssh.close(), sftp.close()

    @api.multi
    def deploy_create_poweruser(self):
        res = super(ClouderBase, self).deploy_create_poweruser()
        if self.application_id.type_id.name == 'drupal':

            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['drush', 'user-create',  self.poweruser_name,  '--password=' + self.poweruser_password, '--mail=' + self.poweruser_email], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            if self.application_id.options()['poweruser_group']['value']:
                self.execute(ssh, ['drush', 'user-add-role', self.application_id.options()['poweruser_group']['value'], self.poweruser_name], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            ssh.close(), sftp.close()

        return res

    @api.multi
    def deploy_test(self):
        res = super(ClouderBase, self).deploy_test()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            if self.application_id.options()['test_install_modules']['value']:
                modules = self.application_id.options()['test_install_modules']['value'].split(',')
                for module in modules:
                    self.execute(ssh, ['drush', '-y', 'en', module], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
                    self.execute(ssh, ['drush', '-y', 'en', module], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            ssh.close(), sftp.close()
        return res


    # def deploy_prepare_apache(self, cr, uid, vals, context=None):
    #     res = super(clouder_base, self).deploy_prepare_apache(cr, uid, vals)
    #     context.update({'clouder-self': self, 'clouder-cr': cr, 'clouder-uid': uid})
    #     if self.application_id.type_id.name == 'odoo':
    #         ssh, sftp = self.connect(vals['proxy_fullname'])
    #         self.execute(ssh, ['sed', '-i', '"s/BASE/' + self.name + '/g"', vals['base_apache_configfile']])
    #         self.execute(ssh, ['sed', '-i', '"s/DOMAIN/' + self.domain_id.name + '/g"', vals['base_apache_configfile']])
    #         self.execute(ssh, ['sed', '-i', '"s/SERVER/' + vals['server_domain'] + '/g"', vals['base_apache_configfile']])
    #         self.execute(ssh, ['sed', '-i', '"s/PORT/' + vals['service_options']['port']['hostport'] + '/g"', vals['base_apache_configfile']])
    #         ssh.close()
    #         sftp.close()
    #     return
    #

    @api.multi
    def post_reset(self):
        res = super(ClouderBase, self).post_reset()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['cp', '-R', self.parent_id.service_id.full_localpath() + '/sites/' + self.parent_id.fulldomain(), self.service_id.full_localpath_files() + '/sites/' + self.fulldomain()])
            ssh.close(), sftp.close()

        return res

    @api.multi
    def update_base(self):
        res = super(ClouderBase, self).update_base()
        if self.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.service_id.container_id.fullname(), username=self.application_id.type_id.system_user)
            self.execute(ssh, ['drush', 'updatedb'], path=self.service_id.full_localpath_files() + '/sites/' + self.fulldomain())
            ssh.close(), sftp.close()

        return res

    @api.multi
    def purge_post(self):
        super(ClouderBase, self).purge_post()
        if self.application_id.type_id.name == 'drupal':

            ssh, sftp = self.connect(self.service_id.container_id.fullname())
            self.execute(ssh, ['rm', '-rf', self.service_id.full_localpath() + '/sites/' + self.fulldomain()])
            self.execute(ssh, ['rm', '-rf', '/etc/nginx/sites-enabled/' + self.fullname()])
            self.execute(ssh, ['rm', '-rf', '/etc/nginx/sites-available/' + self.fullname()])
            self.execute(ssh, ['/etc/init.d/nginx','reload'])
            ssh.close(), sftp.close()

class ClouderSaveSave(models.Model):
    _inherit = 'clouder.save.save'


    @api.multi
    def deploy_base(self):
        res = super(ClouderSaveSave, self).deploy_base()
        if self.base_id.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.container_id.fullname(), username=self.base_id.application_id.type_id.system_user)
#            self.execute(ssh, ['drush', 'archive-dump', self.unique_name_(), '--destination=/base-backup/' + vals['saverepo_name'] + 'tar.gz'])
            self.execute(ssh, ['cp', '-R', self.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain(), '/base-backup/' + self.repo_id.name + '/site'])
            ssh.close(), sftp.close()
        return

    @api.multi
    def restore_base(self):
        res = super(ClouderSaveSave, self).restore_base()
        if self.base_id.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.container_id.fullname(), username=self.base_id.application_id.type_id.system_user)
            self.execute(ssh, ['rm', '-rf', self.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain()])
            self.execute(ssh, ['cp', '-R', '/base-backup/' + self.repo_id.name + '/site', self.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain()])
            ssh.close(), sftp.close()
        return



class ClouderBaseLink(models.Model):
    _inherit = 'clouder.base.link'

    @api.multi
    def deploy_piwik(self, piwik_id):
        super(ClouderBaseLink, self).deploy_piwik(piwik_id)
        if self.name.name.code == 'piwik' and self.base_id.application_id.type_id.name == 'drupal':
            ssh, sftp = self.connect(self.container_id.fullname())
            self.execute(ssh, ['drush', 'variable-set', 'piwik_site_id', piwik_id], path=self.base_id.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain())
            self.execute(ssh, ['drush', 'variable-set', 'piwik_url_http', 'http://' +  self.target.fulldomain() + '/'], path=self.base_id.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain())
            self.execute(ssh, ['drush', 'variable-set', 'piwik_url_https', 'https://' + self.target.fulldomain() + '/'], path=self.base_id.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain())
            self.execute(ssh, ['drush', 'variable-set', 'piwik_privacy_donottrack', '0'], path=self.base_id.service_id.full_localpath_files() + '/sites/' + self.base_id.fulldomain())
            ssh.close(), sftp.close()
        return